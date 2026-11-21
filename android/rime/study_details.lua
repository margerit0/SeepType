-- SPDX-License-Identifier: GPL-3.0-or-later
local function candidate_reading(ctx, env)
  local cand = ctx:get_selected_candidate()
  local genuine = cand and cand:get_genuine()
  local phrase = genuine and genuine:to_phrase()
  if not phrase then return "" end
  local memory = env.memory or env.details_memory
  if not memory then
    memory = Memory(env.engine, env.engine.schema, "translator")
    env.details_memory = memory
  end
  -- Dictionary code, not the typed keys (which can be abbreviated or 双拼).
  return table.concat(memory:decode(phrase.code), " ")
end

return function(keys)
  return {
    init = keys.init,
    fini = function(env)
      if env.details_memory then env.details_memory:disconnect(); env.details_memory = nil end
      keys.fini(env)
    end,
    func = function(key, env)
      if key.keycode ~= 0 or key:release() then return keys.func(key, env) end
      local ctx = env.engine.context
      if ctx:get_property("study_request") ~= "inspect-v1" then return keys.func(key, env) end
      local handled = keys.func(key, env)
      local reading = ""
      if ctx:get_property("study_response") == "inspect-v1" and ctx:get_property("study_target_english") ~= "" then
        local ok, code = pcall(candidate_reading, ctx, env)
        if ok then reading = code end
      end
      ctx:set_property("study_target_reading", reading)
      return handled
    end,
  }
end
