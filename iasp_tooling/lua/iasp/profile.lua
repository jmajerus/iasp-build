-- iasp/profile.lua
-- Build-profile-conditional visibility for Div, Header, and Span elements.
--
-- Markup:
--   ::: {.profile-only profiles="annex1 annex2"}   render only in the listed profiles
--   ::: {.standalone-only}                          render only when build-profile ~= "default"
--
-- The current profile comes from the `build-profile` metadata key, which the
-- builder writes into build/build-metadata.json. When the key is absent the
-- profile is "default" (the main book), so `.standalone-only` content is
-- hidden and `.profile-only` content renders only if "default" is listed.
--
-- When an element is allowed to render, the control classes and the
-- `profiles` attribute are stripped so they never reach the output.

local utils = pandoc.utils

local M = {}

M.DEFAULT_PROFILE = "default"

local CONTROL_CLASSES = {
  ["profile-only"] = true,
  ["standalone-only"] = true,
}

local function trim(value)
  return (tostring(value):gsub("^%s+", ""):gsub("%s+$", ""))
end

--- Resolve the active profile name from a Pandoc Meta table.
function M.current_profile(meta)
  if meta then
    local node = meta["build-profile"]
    if node ~= nil then
      local text = trim(type(node) == "string" and node or utils.stringify(node))
      if text ~= "" then
        return text
      end
    end
  end
  return M.DEFAULT_PROFILE
end

--- Parse a `profiles` attribute ("a b", "a, b", "a,b") into a set.
function M.parse_profiles(value)
  local set = {}
  local count = 0
  if value then
    for token in tostring(value):gmatch("[^%s,]+") do
      set[token] = true
      count = count + 1
    end
  end
  return set, count
end

local function control_classes(el)
  local found = {}
  if not el or not el.classes then
    return found, false
  end
  local any = false
  for _, cls in ipairs(el.classes) do
    local lowered = cls:lower()
    if CONTROL_CLASSES[lowered] then
      found[lowered] = true
      any = true
    end
  end
  return found, any
end

local warned_missing = false

--- Decide whether `el` renders in `profile`.
-- Returns (allowed, mutated). When allowed and the element carried control
-- markup, the markup is stripped in place and mutated is true.
function M.enforce(el, profile)
  local found, any = control_classes(el)
  if not any then
    return true, false
  end

  profile = profile or M.DEFAULT_PROFILE
  local allowed = true

  if found["standalone-only"] and profile == M.DEFAULT_PROFILE then
    allowed = false
  end

  if allowed and found["profile-only"] then
    local raw = el.attributes and el.attributes["profiles"] or nil
    local set, count = M.parse_profiles(raw)
    if count == 0 then
      if not warned_missing then
        io.stderr:write(
          "[iasp-profile] WARNING: .profile-only without a profiles=\"...\" attribute; "
            .. "the element is rendered in every profile.\n"
        )
        warned_missing = true
      end
    elseif not set[profile] then
      allowed = false
    end
  end

  if not allowed then
    return false, false
  end

  local retained = {}
  for _, cls in ipairs(el.classes) do
    if not CONTROL_CLASSES[cls:lower()] then
      table.insert(retained, cls)
    end
  end
  el.classes = retained
  if el.attributes and el.attributes["profiles"] ~= nil then
    el.attributes["profiles"] = nil
  end
  return true, true
end

--- Build a filter table (Div/Header/Span) bound to `profile`.
function M.filter_for(profile)
  local function handler(el)
    local allowed, mutated = M.enforce(el, profile)
    if not allowed then
      return {}
    end
    if mutated then
      return el
    end
    return nil
  end
  return { Div = handler, Header = handler, Span = handler }
end

--- Apply profile visibility to a whole document using its own metadata.
function M.apply_to_document(doc)
  local profile = M.current_profile(doc.meta)
  return doc:walk(M.filter_for(profile))
end

return M
