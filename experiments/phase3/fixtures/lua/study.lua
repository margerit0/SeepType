-- Only this isolated fixture binds F8. It is not a product shortcut.
local core = require("study_core")
local function keys(key, env)
  local ctx = env.engine.context
  if key:release() then return 2 end
  if key.keycode == 0xffc5 and not key:ctrl() and not key:alt() then
    ctx:set_option("learning_mode", not ctx:get_option("learning_mode"))
    ctx:refresh_non_confirmed_composition()
    return 1
  end
  return core.keys.func(key, env)
end
return {filter = core.filter, keys = {init = core.keys.init, func = keys}}
