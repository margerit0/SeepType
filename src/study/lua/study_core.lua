-- Offline candidate annotations and the single authoritative English action.
-- Context properties are transient, per-session data. Nothing is logged here.
local loaded, words = pcall(require, "lexicon")
if not loaded or type(words) ~= "table" then words = {}; loaded = false end
for zh, en in pairs(words) do
  if type(zh) ~= "string" or type(en) ~= "string" or en == ""
      or #en > 2048 or en:find("[%z\1-\31\127]") then
    words[zh] = nil
  end
end

local function init(env)
  local ctx = env.engine.context
  ctx:set_property("study_load_state", loaded and "ready" or "missing")
  ctx:set_property("study_protocol", "1")
end

local function filter(input, env)
  local enabled = env.engine.context:get_option("learning_mode")
  for cand in input:iter() do
    if enabled then
      -- Hide unrelated upstream comments from the English row. The genuine
      -- candidate, its original comment, ranking and Chinese selection survive.
      yield(ShadowCandidate(cand, cand.type, cand.text, words[cand.text] or ""))
    else
      yield(cand)
    end
  end
end

local function describe(ctx)
  local cand = ctx:get_selected_candidate()
  if not ctx:get_option("learning_mode") then return "disabled", cand, "" end
  if not cand then return "no-candidate", nil, "" end
  local en = words[cand.text] or ""
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
  local reason, cand, en = describe(ctx)
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
      local reason, cand, en = describe(ctx)
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

return {filter = {init = init, func = filter}, keys = {init = init, func = keys}}
