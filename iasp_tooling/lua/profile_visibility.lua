-- profile_visibility.lua
-- Remove `.profile-only` / `.standalone-only` content that does not belong to
-- the active build profile (metadata key `build-profile`, default "default").
-- Runs before the other filters, including in draft builds that skip the
-- semantic filters, so hidden content never reaches later stages.
-- See iasp/profile.lua for the markup rules.

local path = pandoc.path
local script_dir = (PANDOC_SCRIPT_FILE and path.directory(PANDOC_SCRIPT_FILE)) or "."
package.path = package.path .. ";" .. script_dir .. "/?.lua;" .. script_dir .. "/?/init.lua"

local profile = require("iasp.profile")

return {
  { Pandoc = profile.apply_to_document },
}
