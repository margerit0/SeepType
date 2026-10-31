-- Minimal spike: no network, per-key file I/O, input history, or core patch.
local ok, words = pcall(require, "lexicon")
if not ok or type(words) ~= "table" then words = {}; ok = false end
-- Reject malformed entries rather than attach arbitrary Lua values to candidates.
for zh, en in pairs(words) do
  if type(zh) ~= "string" or type(en) ~= "string" or en == "" then
    words[zh] = nil
  end
end

local function init(env)
  env.engine.context:set_property("study_load_state", ok and "ready" or "missing")
end

local function filter(input, env)
  local enabled = env.engine.context:get_option("learning_mode")
  for cand in input:iter() do
    local en = enabled and words[cand.text]
    if en then
      -- A wrapper preserves the engine candidate and its original comment.
      yield(ShadowCandidate(cand, cand.type, cand.text, en))
    else
      yield(cand)
    end
  end
end

local function keys(key, env)
  local ctx = env.engine.context
  if key:release() then return 2 end
  -- F8 exists only as an experiment toggle, not a new approved product shortcut.
  if key.keycode == 0xffc5 and not key:ctrl() and not key:alt() then
    ctx:set_option("learning_mode", not ctx:get_option("learning_mode"))
    ctx:refresh_non_confirmed_composition()
    return 1
  end
  if key.keycode ~= 0xff0d or not key:ctrl() or not key:shift()
      or key:alt() or key:super() then return 2 end
  local cand = ctx:get_selected_candidate()
  local reason
  if not ctx:get_option("learning_mode") then reason = "disabled"
  elseif not cand then reason = "no-candidate"
  elseif cand._start ~= 0 or cand._end ~= #ctx.input or ctx.caret_pos ~= #ctx.input then
    reason = "partial-composition"
  elseif not words[cand.text] then reason = "no-definition" end
  if reason then
    ctx:set_property("study_action", reason)
    return 1 -- Do not let a rejected English action commit Chinese/raw pinyin.
  end
  local en = words[cand.text] -- Complete value, never a truncated UI comment.
  env.engine:commit_text(en)
  ctx:clear()
  ctx:set_property("study_action", "english-committed")
  return 1
end

return { filter = {init = init, func = filter}, keys = {init = init, func = keys} }
