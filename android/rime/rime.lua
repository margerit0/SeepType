-- SPDX-License-Identifier: GPL-3.0-or-later
-- Android keeps the verified shared filter/commit behavior and adds a read-only
-- pronunciation hint for the detail card's local asset lookup.
-- Add separately sourced Android names before the shared core reads its lexicon.
-- Never replace a Windows entry or its default sense, even if the readings differ.
local base_ok, base = pcall(require, "lexicon")
local names_ok, names = pcall(require, "study_offline_names_en")
if base_ok and type(base) == "table" and base.schema_version == 2 and type(base.entries) == "table"
    and names_ok and type(names) == "table" then
  for word, entry in pairs(names) do
    if base.entries[word] == nil then base.entries[word] = entry end
  end
end
local core = require("study_core")
study_filter = core.filter
study_keys = require("study_details")(core.keys)
