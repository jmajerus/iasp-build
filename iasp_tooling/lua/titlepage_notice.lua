-- titlepage_notice.lua
-- Helper filter used by build_book.py to render the `titlepage-notice`
-- metadata value as a standalone fragment (LaTeX for PDF, HTML for EPUB).
-- The document body is replaced with the notice; an empty body means
-- "no notice".
--
-- Accepted metadata:
--   titlepage-notice: <Markdown>   render this text
--   titlepage-notice: rights       reuse the `rights` value
--   titlepage-notice: true         same as `rights`
--   titlepage-rights: true         same as `rights` (when titlepage-notice is absent)
--
-- When the builder sets `iasp-titlepage-notice-target: epub` and the notice
-- is the `rights` value, the body stays empty: pandoc's EPUB title page
-- already prints `rights`, so injecting it again would duplicate it.

local utils = pandoc.utils

local function trim(value)
  return (tostring(value):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function is_true(node)
  if node == nil then
    return false
  end
  if utils.type(node) == "boolean" then
    return node
  end
  local lowered = trim(utils.stringify(node)):lower()
  return lowered == "true" or lowered == "yes" or lowered == "on" or lowered == "1"
end

local function to_blocks(node)
  if node == nil then
    return nil
  end
  local kind = utils.type(node)
  if kind == "Blocks" then
    return node
  elseif kind == "Inlines" then
    return pandoc.Blocks({ pandoc.Plain(node) })
  elseif kind == "string" then
    return pandoc.read(node, "markdown").blocks
  end
  local text = trim(utils.stringify(node))
  if text == "" then
    return nil
  end
  return pandoc.read(text, "markdown").blocks
end

-- Returns (value, from_rights)
local function resolve(meta)
  local notice = meta["titlepage-notice"]
  if notice ~= nil then
    if utils.type(notice) == "boolean" then
      if notice then
        return meta["rights"], true
      end
      return nil, false
    end
    local text = trim(utils.stringify(notice)):lower()
    if text == "" or text == "false" or text == "no" or text == "off" then
      return nil, false
    end
    if text == "rights" or text == "true" or text == "yes" then
      return meta["rights"], true
    end
    return notice, false
  end
  if is_true(meta["titlepage-rights"]) then
    return meta["rights"], true
  end
  return nil, false
end

function Pandoc(doc)
  local value, from_rights = resolve(doc.meta)
  local target = trim(utils.stringify(doc.meta["iasp-titlepage-notice-target"] or "")):lower()
  local blocks = nil
  if value ~= nil and not (from_rights and target == "epub") then
    blocks = to_blocks(value)
  end
  return pandoc.Pandoc(blocks or {}, doc.meta)
end
