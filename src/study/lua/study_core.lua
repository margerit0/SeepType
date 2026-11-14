-- Offline candidate annotations and the single authoritative English action.
-- Context properties are transient, per-session data. Nothing is logged here.
local loaded, data = pcall(require, "lexicon")
local words = {}
local needs_readings = false
local function valid_english(en)
  return type(en) == "string" and en ~= "" and #en <= 2048
      and not en:find("[%z\1-\31\127]")
end
if not loaded or type(data) ~= "table" then
  loaded = false
elseif data.schema_version == 2 then
  -- Keep all reviewed senses in the data, but use the explicitly selected
  -- common sense for the existing single-definition candidate interaction.
  if type(data.entries) ~= "table" then
    loaded = false
  else
    for zh, entry in pairs(data.entries) do
      if type(zh) == "string" and type(entry) == "table"
          and type(entry.primary_sense_id) == "string" and type(entry.senses) == "table" then
        local function value_for(id)
          local chosen, matches = nil, 0
          for _, sense in ipairs(entry.senses) do
            if type(sense) == "table" and sense.id == id then
              matches = matches + 1
              if valid_english(sense.commit_english)
                  and sense.display_english == sense.commit_english then
                chosen = sense.commit_english
              end
            end
          end
          if matches == 1 then return chosen end
        end
        if entry.requires_reading == true and type(entry.primary_by_reading) == "table" then
          local readings, valid = {}, true
          for code, id in pairs(entry.primary_by_reading) do
            local en = value_for(id)
            if type(code) ~= "string" or code == "" or code:find("[^a-z ]") or not en then
              valid = false
            else
              readings[code] = en
            end
          end
          if valid and next(readings) then words[zh] = readings; needs_readings = true end
        elseif entry.requires_reading == nil or entry.requires_reading == false then
          words[zh] = value_for(entry.primary_sense_id)
        end
      end
    end
  end
elseif data.schema_version == nil then
  -- Original 200-entry development previews remain supported.
  for zh, en in pairs(data) do
    if type(zh) == "string" and valid_english(en) then words[zh] = en end
  end
else
  loaded = false
end

local function init(env)
  local ctx = env.engine.context
  ctx:set_property("study_load_state", loaded and "ready" or "missing")
  ctx:set_property("study_protocol", "1")
  if needs_readings then env.memory = Memory(env.engine, env.engine.schema, "translator") end
end

local function fini(env)
  if env.memory then env.memory:disconnect(); env.memory = nil end
end

local function definition(cand, env)
  local value = words[cand.text]
  if type(value) == "string" then return value end
  if type(value) ~= "table" or not env.memory then return "" end
  -- Decode the actual dictionary phrase, including for abbreviated and
  -- double-pinyin input; raw key text is not a reliable pronunciation.
  local genuine = cand:get_genuine()
  local phrase = genuine and genuine:to_phrase()
  if not phrase then return "" end
  local reading = table.concat(env.memory:decode(phrase.code), " ")
  return value[reading] or ""
end

local function filter(input, env)
  local enabled = env.engine.context:get_option("learning_mode")
  for cand in input:iter() do
    if enabled then
      -- Hide unrelated upstream comments from the English row. The genuine
      -- candidate, its original comment, ranking and Chinese selection survive.
      yield(ShadowCandidate(cand, cand.type, cand.text, definition(cand, env)))
    else
      yield(cand)
    end
  end
end

local function describe(ctx, env)
  local cand = ctx:get_selected_candidate()
  if not ctx:get_option("learning_mode") then return "disabled", cand, "" end
  if not cand then return "no-candidate", nil, "" end
  local en = definition(cand, env)
  if cand._start ~= 0 or cand._end ~= #ctx.input or ctx.caret_pos ~= #ctx.input then
    return "partial-composition", cand, en
  end
  if en == "" then return "no-definition", cand, "" end
  return "ready", cand, en
end

local function publish(ctx, response, reason, cand, en)
  ctx:set_property("study_target_text", cand and cand.text or "")
  ctx:set_property("study_target_english", en)
  ctx:set_property("study_target_reason", reason)
  -- Publish the response marker last, so an incomplete response fails closed.
  ctx:set_property("study_response", response)
end

local function commit(env)
  local ctx = env.engine.context
  local reason, cand, en = describe(ctx, env)
  if reason ~= "ready" then
    ctx:set_property("study_action", reason)
    return 1 -- Consume the explicit action without committing raw input.
  end
  env.engine:commit_text(en) -- Complete dictionary value, never UI ellipsis.
  ctx:clear()
  ctx:set_property("study_action", "english-committed")
  return 1
end

local function keys(key, env)
  if key:release() then return 2 end
  local ctx = env.engine.context
  -- Private frontend command. Key code zero is never emitted by the host's
  -- physical-key path; the request is cleared even when it is unrecognized.
  -- Inspection cannot commit or consume the application's pending commit.
  if key.keycode == 0 then
    local request = ctx:get_property("study_request")
    if request == "" then return 2 end
    ctx:set_property("study_request", "")
    if request == "inspect-v1" then
      local reason, cand, en = describe(ctx, env)
      publish(ctx, request, reason, cand, en)
      return 1
    elseif request == "commit-v1" then
      local handled = commit(env)
      ctx:set_property("study_response", request)
      return handled
    end
    ctx:set_property("study_action", "unavailable")
    return 1
  end
  if key.keycode == 0xff0d and key:ctrl() and key:shift()
      and not key:alt() and not key:super() then
    return commit(env)
  end
  return 2
end

return {filter = {init = init, fini = fini, func = filter}, keys = {init = init, fini = fini, func = keys}}
