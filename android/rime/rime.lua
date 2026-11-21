-- SPDX-License-Identifier: GPL-3.0-or-later
-- Android keeps the verified shared filter/commit behavior and adds a read-only
-- pronunciation hint for the detail card's local asset lookup.
local core = require("study_core")
study_filter = core.filter
study_keys = require("study_details")(core.keys)
