-- iasp-semantics.lua
-- Map EPUB 3 structural semantics (epub:type)
-- to sensible LaTeX/PDF behavior while keeping authoring ergonomics light.
--
-- The filter runs in two passes:
--   1. Preprocess Markdown-derived blocks so shorthand fenced divs such as
--      "::: callout" or "::: note" are converted into proper Div elements with
--      semantic classes.
--   2. Apply epub:type aliases plus PDF-specific wrapping (sidebars, callouts,
--      etc.) via the standard element handlers.

local utils = pandoc.utils
local path = pandoc.path
local system = pandoc.system

local document_meta = {}
local build_stage_cache = nil
local article_mode_cache = nil
local frontmatter_enabled_cache = nil
local backmatter_enabled_cache = nil

local function capture_document_meta(meta)
  document_meta = {}
  build_stage_cache = nil
  article_mode_cache = nil
  frontmatter_enabled_cache = nil
  backmatter_enabled_cache = nil
  if meta then
    for key, value in pairs(meta) do
      document_meta[key] = value
    end
  end
  return nil
end

local function meta_value(key)
  if not document_meta or not key then
    return nil
  end

  local node = document_meta[key]
  if not node then
    return nil
  end

  return utils.stringify(node)
end

local function truthy_string(value)
  if value == nil then
    return false
  end
  local lowered = tostring(value):lower()
  return lowered == "1" or lowered == "true" or lowered == "yes" or lowered == "on"
end

local function article_build_enabled()
  if article_mode_cache ~= nil then
    return article_mode_cache
  end
  article_mode_cache = truthy_string(meta_value("article-build"))
  return article_mode_cache
end

local function resolve_toggle(meta_key, default_state)
  local value = meta_value(meta_key)
  if value ~= nil and value ~= "" then
    return truthy_string(value)
  end
  return default_state
end

local function frontmatter_enabled()
  if frontmatter_enabled_cache ~= nil then
    return frontmatter_enabled_cache
  end
  frontmatter_enabled_cache = resolve_toggle("frontmatter-enabled", not article_build_enabled())
  return frontmatter_enabled_cache
end

local function backmatter_enabled()
  if backmatter_enabled_cache ~= nil then
    return backmatter_enabled_cache
  end
  backmatter_enabled_cache = resolve_toggle("backmatter-enabled", not article_build_enabled())
  return backmatter_enabled_cache
end

local function enforce_section_visibility(el)
  if not el or not el.classes then
    return true, false
  end

  for _, cls in ipairs(el.classes) do
    local lowered = cls:lower()
    if lowered == "frontmatter" and not frontmatter_enabled() then
      return false, false
    end
    if lowered == "backmatter" and not backmatter_enabled() then
      return false, false
    end
  end

  return true, false
end

local function normalize_stage_value(value)
  if not value then
    return nil
  end
  local lowered = tostring(value):lower()
  if lowered == "draft" or lowered == "final" then
    return lowered
  end
  return nil
end

local function current_build_stage()
  if build_stage_cache then
    return build_stage_cache
  end

  local from_meta = normalize_stage_value(meta_value("build-stage"))
  if from_meta then
    build_stage_cache = from_meta
    return build_stage_cache
  end

  if truthy_string(meta_value("draft-build")) then
    build_stage_cache = "draft"
    return build_stage_cache
  end

  if truthy_string(meta_value("final-build")) then
    build_stage_cache = "final"
    return build_stage_cache
  end

  build_stage_cache = "final"
  return build_stage_cache
end

local function stage_class_from_element(el)
  if not el or not el.classes then
    return nil
  end
  for _, cls in ipairs(el.classes) do
    local lowered = cls:lower()
    if lowered == "draft" or lowered == "final" then
      return lowered
    end
  end
  return nil
end

local function enforce_stage_visibility(el)
  if not el then
    return true, false
  end

  local stage_class = stage_class_from_element(el)
  if not stage_class then
    return true, false
  end

  local stage = current_build_stage()
  local should_render = (stage_class == "draft" and stage == "draft")
    or (stage_class == "final" and stage ~= "draft")

  if not should_render then
    return false, false
  end

  local retained = {}
  for _, cls in ipairs(el.classes) do
    local lowered = cls:lower()
    if lowered ~= "draft" and lowered ~= "final" then
      table.insert(retained, cls)
    end
  end

  local mutated = #retained ~= #el.classes
  el.classes = retained
  return true, mutated
end

-- Helper: does this element's attributes include a given epub:type?
local function has_epub_type(attr, target)
  local val = attr and attr["epub:type"]
  if not val then return false end
  for token in val:gmatch("%S+") do
    if token == target then
      return true
    end
  end
  return false
end

local function wrap_in_env(div, env_name)
  local blocks = {}
  table.insert(blocks, pandoc.RawBlock("latex", "\\begin{" .. env_name .. "}\n"))
  for _, b in ipairs(div.content) do
    table.insert(blocks, b)
  end
  table.insert(blocks, pandoc.RawBlock("latex", "\\end{" .. env_name .. "}\n"))
  return blocks
end

local function add_unique(tbl, value)
  for _, existing in ipairs(tbl) do
    if existing == value then
      return
    end
  end
  table.insert(tbl, value)
end

local function has_class(el, class_name)
  if not el or not el.classes then return false end
  for _, cls in ipairs(el.classes) do
    if cls == class_name then
      return true
    end
  end
  return false
end

local function span_with_classes(inlines, classes)
  local class_list
  if type(classes) == "string" then
    class_list = { classes }
  else
    class_list = classes or {}
  end
  return pandoc.Span(inlines, pandoc.Attr("", class_list, {}))
end

local function is_trivial_raw_latex(block)
  if not block or block.t ~= "RawBlock" or block.format ~= "latex" then
    return false
  end

  local text = block.text or ""
  if text == "" then
    return true
  end

  if text:match("\\hypertarget") or text:match("\\label") or text:match("\\phantomsection") then
    return true
  end

  if text:match("^%s*$") then
    return true
  end

  return false
end

local function begins_with_level_one_header(blocks)
  if not blocks or #blocks == 0 then
    return false
  end

  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      return (block.level or 0) == 1
    elseif is_trivial_raw_latex(block) then
      -- ignore anchor housekeeping emitted ahead of headers
    elseif block.t == "Div" and (not block.content or #block.content == 0) then
      -- skip empty wrappers
    else
      return false
    end
  end

  return false
end

local function latex_escape_argument(text)
  if not text or text == "" then
    return ""
  end

  local replacements = {
    ["\\"] = "\\textbackslash{}",
    ["{"] = "\\{",
    ["}"] = "\\}",
    ["%"] = "\\%",
    ["$"] = "\\$",
    ["#"] = "\\#",
    ["&"] = "\\&",
    ["_"] = "\\_",
    ["^"] = "\\^{}",
    ["~"] = "\\~{}"
  }

  return text:gsub(".", function(char)
    return replacements[char] or char
  end)
end

local SIDEBAR_GLYPH_UTF8 = "🗒"
local SIDEBAR_BADGE_LABEL = "SIDEBAR"
local SECTION_HEADING_GLYPH_CLASS = "section-heading-glyph"

local function replace_meta_placeholders(str)
  if not str or str.t ~= "Str" then
    return nil
  end

  local changed = false
  local text = str.text
  text = text:gsub("({{%s*meta:([%w_%.-]+)%s*}})", function(full, key)
    local value = meta_value(key)
    if value and value ~= "" then
      changed = true
      return value
    end
    return full
  end)

  if changed then
    str.text = text
    return str
  end

  return nil
end

local function sidebar_glyph_inlines()
  if FORMAT:match("latex") then
    return { pandoc.RawInline("latex", "\\sidebarheadingglyph{}") }
  end
  return { pandoc.Str(SIDEBAR_GLYPH_UTF8), pandoc.Space() }
end

local function section_heading_glyph_inlines(glyph_text)
  if not glyph_text or glyph_text == "" then
    return nil
  end

  if FORMAT:match("latex") then
    return {
      pandoc.RawInline("latex", "\\sectionheadingglyph{" .. latex_escape_argument(glyph_text) .. "}"),
      pandoc.Space()
    }
  end

  local glyph_span = span_with_classes({ pandoc.Str(glyph_text) }, { SECTION_HEADING_GLYPH_CLASS })
  return { glyph_span, pandoc.Space() }
end

local function sidebar_inline_marker_inlines()
  if FORMAT:match("latex") then
    return { pandoc.RawInline("latex", "\\sidebarinlineglyph{}") }
  end

  local span = span_with_classes({ pandoc.Str(SIDEBAR_GLYPH_UTF8) }, { "sidebar-inline-glyph" })
  return { span, pandoc.Space() }
end

local function sidebar_badge_blocks()
  if FORMAT:match("latex") then
    return { pandoc.RawBlock("latex", "\\sidebarbadge\n") }
  end

  local glyph_span = span_with_classes({ pandoc.Str(SIDEBAR_GLYPH_UTF8) }, { "sidebar-badge__glyph" })
  local label_span = span_with_classes({ pandoc.Str(SIDEBAR_BADGE_LABEL) }, { "sidebar-badge__label" })
  local badge_span = span_with_classes({ glyph_span, pandoc.Space(), label_span }, { "sidebar-badge" })
  return { pandoc.Para({ badge_span }) }
end

local function header_has_sidebar_glyph(header)
  if not header or not header.content or #header.content == 0 then
    return false
  end

  local first = header.content[1]
  if not first then
    return false
  end

  if first.t == "RawInline" and first.format == "latex" and first.text:find("\\sidebarheadingglyph") then
    return true
  end

  if first.t == "Str" and first.text and first.text:find("^" .. SIDEBAR_GLYPH_UTF8) then
    return true
  end

  return false
end

local function inject_sidebar_glyph(header)
  if not header or header.t ~= "Header" then
    return false
  end

  if header_has_sidebar_glyph(header) then
    return false
  end

  header.content = header.content or {}
  local glyph_inlines = sidebar_glyph_inlines()
  for idx = #glyph_inlines, 1, -1 do
    table.insert(header.content, 1, glyph_inlines[idx])
  end
  return true
end

local function header_has_section_heading_glyph(header)
  if not header or not header.content or #header.content == 0 then
    return false
  end

  local first = header.content[1]
  if not first then
    return false
  end

  if first.t == "Span" and has_class(first, SECTION_HEADING_GLYPH_CLASS) then
    return true
  end

  if first.t == "RawInline" and first.format == "latex" and first.text:find("\\sectionheadingglyph") then
    return true
  end

  return false
end

local function inject_section_heading_glyph(header, glyph_text)
  if not header or header.t ~= "Header" then
    return false
  end

  if header_has_section_heading_glyph(header) then
    return false
  end

  local glyph_inlines = section_heading_glyph_inlines(glyph_text)
  if not glyph_inlines then
    return false
  end

  header.content = header.content or {}
  for idx = #glyph_inlines, 1, -1 do
    table.insert(header.content, 1, glyph_inlines[idx])
  end

  return true
end

local function apply_section_heading_glyph(blocks, glyph_text)
  if not glyph_text or glyph_text == "" or not blocks then
    return
  end

  local inserted = false

  local function walk(block_list)
    if inserted or not block_list then
      return
    end

    for _, block in ipairs(block_list) do
      if inserted then
        break
      end

      if block.t == "Div" then
        if has_class(block, "section") then
          for _, inner in ipairs(block.content or {}) do
            if inner.t == "Header" then
              if inject_section_heading_glyph(inner, glyph_text) then
                inserted = true
                break
              end
            end
          end
        end
        walk(block.content)
      elseif block.t == "Header" then
        if inject_section_heading_glyph(block, glyph_text) then
          inserted = true
          break
        end
      end
    end
  end

  walk(blocks)
end

local function decorate_sidebar_heading(blocks)
  if not blocks then
    return false
  end

  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      return inject_sidebar_glyph(block)
    end
  end

  return false
end

local function insert_sidebar_badge(div)
  if not div or not div.content then
    return false
  end

  local badge_blocks = sidebar_badge_blocks()
  for idx = #badge_blocks, 1, -1 do
    table.insert(div.content, 1, badge_blocks[idx])
  end

  return true
end

local function inject_sidebar_inline_marker(div)
  if not div or not div.content then
    return false
  end

  for _, block in ipairs(div.content) do
    if block.t == "Para" or block.t == "Plain" then
      local marker_inlines = sidebar_inline_marker_inlines()
      for idx = #marker_inlines, 1, -1 do
        table.insert(block.content, 1, marker_inlines[idx])
      end
      return true
    elseif block.t == "Header" then
      break
    end
  end

  return false
end

local function expand_compound_classes(el)
  if not el or not el.classes then
    return false
  end

  local normalized = {}
  local mutated = false

  for _, cls in ipairs(el.classes) do
    local value = cls:lower()
    if value:find(".", 1, true) then
      mutated = true
      for chunk in value:gmatch("[^%.]+") do
        if chunk ~= "" then
          add_unique(normalized, chunk)
        end
      end
    else
      add_unique(normalized, value)
    end
  end

  if mutated or #normalized ~= #el.classes then
    el.classes = normalized
    return true
  end

  return false
end

-- Allow Markdown shorthand classes to add the matching epub:type automatically.
local SEMANTIC_CLASS_MAP = {
  callout = "callout",
  note = "note",
  example = "example",
  definition = "definition",
  sidebar = "aside",
  aside = "aside",
  ["sidebar-inline"] = "sidebar-inline",
  epigraph = "epigraph",
  ["epigraph-inline"] = "epigraph-inline",
  part = "part",
  chapter = "chapter",
  appendix = "appendix",
  subchapter = "subchapter",
  section = "section",
  subsection = "subsection",
  frontmatter = "frontmatter",
  backmatter = "backmatter",
  toc = "toc",
  dedication = "dedication",
  preface = "preface",
  introduction = "introduction",
  conclusion = "conclusion",
  epilogue = "epilogue",
  prologue = "prologue",
  foreword = "foreword",
  afterword = "afterword",
  acknowledgments = "acknowledgments",
  acknowledgment = "acknowledgments",
  summary = "summary",
  abstract = "abstract",
  contribution = "contribution",
  colophon = "colophon",
  footnotes = "footnotes",
  glossary = "glossary",
  index = "index",
  bibliography = "bibliography",
  references = "references",
  figure = "figure",
  table = "table",
  erratum = "erratum",
  bridge = "bridge",
  bridgehead = "bridge"
}

local ARIA_ROLE_MAP = {
  aside = "complementary",
  toc = "doc-toc",
  dedication = "doc-dedication",
  epigraph = "doc-epigraph",
  preface = "doc-preface",
  introduction = "doc-introduction",
  conclusion = "doc-conclusion",
  epilogue = "doc-epilogue",
  chapter = "doc-chapter",
  part = "doc-part",
  appendix = "doc-appendix",
  footnotes = "doc-endnotes",
  glossary = "doc-glossary",
  acknowledgments = "doc-acknowledgments",
  summary = "doc-abstract",
  abstract = "doc-abstract",
  bridge = "complementary"
}

local LOW_PRIORITY_ARIA = {}

local HEADER_ROLE_ALLOWLIST = {
  heading = true,
  none = true,
  presentation = true,
  tab = true
}

local function scrub_header_role(attr)
  if not attr then
    return false
  end

  local role = attr["role"]
  if not role then
    return false
  end

  if not HEADER_ROLE_ALLOWLIST[role] then
    attr["role"] = nil
    return true
  end

  return false
end

local DEPRECATED_TYPE_MAP = {
  sidebar = "aside",
  bridgehead = "bridge"
}

local function normalize_epub_type(attr)
  if not attr then
    return false
  end

  local value = attr["epub:type"]
  if not value or value == "" then
    return false
  end

  local tokens = {}
  local mutated = false

  for token in value:gmatch("%S+") do
    local lowered = token:lower()
    local mapped = DEPRECATED_TYPE_MAP[lowered]
    local replacement = mapped or token
    if mapped then
      mutated = true
    end
    add_unique(tokens, replacement)
  end

  local combined = table.concat(tokens, " ")
  if combined ~= value then
    attr["epub:type"] = combined
    mutated = true
  end

  return mutated
end

local function assign_aria_role(attr)
  if not attr then
    return
  end

  if attr["role"] then
    return
  end

  local epub_type = attr["epub:type"]
  if not epub_type then
    return
  end

  local fallback = nil
  for token in epub_type:gmatch("%S+") do
    local role = ARIA_ROLE_MAP[token]
    if role then
      if not LOW_PRIORITY_ARIA[token] then
        attr["role"] = role
        return
      end
      fallback = fallback or role
    end
  end

  if fallback then
    attr["role"] = fallback
  end
end

local function add_epub_type_token(attr, token)
  if not attr then return false end
  local current = attr["epub:type"]
  if not current or current == "" then
    attr["epub:type"] = token
    return true
  end

  for existing in current:gmatch("%S+") do
    if existing == token then
      return false
    end
  end

  attr["epub:type"] = current .. " " .. token
  return true
end

local function apply_semantic_aliases(el)
  if not el then
    return false
  end

  local mutated = expand_compound_classes(el)

  if not el.classes or #el.classes == 0 then
    return mutated
  end

  el.attributes = el.attributes or {}
  local alias_changed = normalize_epub_type(el.attributes)

  for _, cls in ipairs(el.classes) do
    local mapped = SEMANTIC_CLASS_MAP[cls]
    if mapped then
      if add_epub_type_token(el.attributes, mapped) then
        alias_changed = true
      end
    end
  end

  assign_aria_role(el.attributes)

  return mutated or alias_changed
end

-- ---------------------------------------------------------------------------
-- Shorthand fenced divs (e.g., "::: callout" ... ":::")
-- ---------------------------------------------------------------------------

local SHORTHAND_BASES = {
  callout = true,
  note = true,
  example = true,
  definition = true,
  sidebar = true,
  aside = true,
  ["sidebar-inline"] = true,
  include = true
}

local function parse_shorthand_marker(text)
  local body = text:match("^:::%s*(.-)%s*$")
  if not body or body == "" then
    return nil
  end

  local head, rest = body:match("^([^%s]+)%s*(.*)$")
  if not head or head == "" then
    return nil
  end

  local classes = {}
  for part in head:gmatch("[^%.]+") do
    local lowered = part:lower()
    if lowered ~= "" then
      table.insert(classes, lowered)
    end
  end

  if #classes == 0 then
    return nil
  end

  local base = classes[1]
  if not SHORTHAND_BASES[base] then
    return nil
  end

  local normalized = {}
  for _, cls in ipairs(classes) do
    add_unique(normalized, cls)
  end

  local attributes = {}
  if rest and rest ~= "" then
    for key, value in rest:gmatch('([%w_%-%:]+)%s*=%s*"(.-)"') do
      attributes[key] = value
    end
    for key, value in rest:gmatch("([%w_%-%:]+)%s*=%s*'(.-)'") do
      attributes[key] = value
    end
  end

  return {
    base = base,
    classes = normalized,
    attributes = attributes
  }
end

local function shorthand_is_closer(block)
  if block.t ~= "Para" and block.t ~= "Plain" then
    return false
  end

  local text = utils.stringify(block)
  return text:match("^:::%s*$") ~= nil
end

local function convert_shorthand_blocks(blocks)
  local out = {}
  local i = 1

  while i <= #blocks do
    if blocks[i].t == "Div" and blocks[i].content then
      blocks[i].content = convert_shorthand_blocks(blocks[i].content)
    end

    local token = nil

    if blocks[i].t == "Para" or blocks[i].t == "Plain" then
      token = parse_shorthand_marker(utils.stringify(blocks[i]))
    end

    if token then
      local inner = {}
      local j = i + 1
      local closed = false

      while j <= #blocks do
        if shorthand_is_closer(blocks[j]) then
          closed = true
          break
        end
        table.insert(inner, blocks[j])
        j = j + 1
      end

      if closed then
        local attr = pandoc.Attr("", token.classes, token.attributes or {})
        local div = pandoc.Div(inner, attr)
        table.insert(out, div)
        i = j + 1
        goto continue
      end
      -- If no closer is found, fall through and treat text literally.
    end

    table.insert(out, blocks[i])
    i = i + 1
    ::continue::
  end

  return out
end

local function preprocess_shorthand(doc)
  capture_document_meta(doc.meta)
  doc.blocks = convert_shorthand_blocks(doc.blocks)
  return doc
end

-- ---------------------------------------------------------------------------
-- Include directives (::: include path="file.md" :::)
-- ---------------------------------------------------------------------------

local include_stack = {}

local function attr_truthy(value)
  if value == nil then
    return false
  end
  local lowered = tostring(value):lower()
  return lowered == "1" or lowered == "true" or lowered == "yes" or lowered == "on"
end

local function normalize_newlines(text)
  if not text then
    return ""
  end
  local result = text:gsub("\r\n", "\n")
  result = result:gsub("\r", "\n")
  return result
end

local function slugify_identifier_source(raw)
  if not raw or raw == "" then
    return nil
  end

  if utils and utils.slugify then
    local via_util = utils.slugify(raw)
    if via_util and via_util ~= "" then
      return via_util
    end
  end

  local lowered = raw:lower()
  lowered = lowered:gsub("[^%w]+", "-")
  lowered = lowered:gsub("-+", "-")
  lowered = lowered:gsub("^-+", "")
  lowered = lowered:gsub("-+$", "")

  if lowered == "" then
    return nil
  end

  return lowered
end

local function namespace_header_identifiers(blocks, prefix, min_level)
  if not blocks or not prefix or prefix == "" then
    return blocks
  end

  local threshold = min_level or 2
  local replacements = {}

  local function header_handler(h)
    local level = h.level or 0
    if level >= threshold and h.identifier and h.identifier ~= "" then
      local old_id = h.identifier
      local new_id = prefix .. "-" .. old_id
      replacements[old_id] = new_id
      h.identifier = new_id
      return h
    end
    return nil
  end

  local function link_handler(el)
    local target = el.target
    if target and target:sub(1, 1) == "#" then
      local bare = target:sub(2)
      local mapped = replacements[bare]
      if mapped then
        el.target = "#" .. mapped
        return el
      end
    end
    return nil
  end

  local container = pandoc.Div(blocks)
  container = pandoc.walk_block(container, {
    Header = header_handler,
    Link = link_handler,
  })
  return container.content
end

local function build_literal_code_block(raw, div, attrs)
  local normalized = normalize_newlines(raw)
  local identifier = ""
  if div.identifier and div.identifier ~= "" then
    identifier = div.identifier
  elseif attrs.id and attrs.id ~= "" then
    identifier = attrs.id
  end

  local classes = {}
  if div.classes then
    for _, cls in ipairs(div.classes) do
      if cls ~= "include" then
        table.insert(classes, cls)
      end
    end
  end

  local attributes = {}
  local lang = attrs.lang or attrs.language
  if lang and lang ~= "" then
    attributes.lang = lang
  end

  return pandoc.CodeBlock(normalized, pandoc.Attr(identifier, classes, attributes))
end

local function resolve_include_path(target)
  if not target or target == "" then
    return nil
  end

  if path and path.is_absolute and path.is_absolute(target) then
    return target
  end

  local cwd = system.get_working_directory()
  if path and path.normalize then
    return path.normalize(cwd .. "/" .. target)
  end
  return cwd .. "/" .. target
end

local function path_is_dir(target)
  local stat = io.popen("test -d '" .. target .. "' && echo dir\n")
  if not stat then
    return false
  end
  local result = stat:read("*l")
  stat:close()
  return result == "dir"
end

local function basename_without_ext(raw)
  if not raw or raw == "" then
    return nil
  end

  local trimmed = raw:gsub("[\\/]+$", "")
  if trimmed == "" then
    trimmed = raw
  end

  local filename
  if path and path.filename then
    filename = path.filename(trimmed)
  else
    filename = trimmed:match("([^/\\]+)$") or trimmed
  end

  if not filename or filename == "" then
    filename = trimmed
  end

  local base = filename:match("^(.*)%.([^%.]+)$")
  if base and base ~= "" then
    return base
  end

  return filename
end

local function list_markdown_files(dir)
  local files = {}
  local p = io.popen("ls -1 '" .. dir .. "'")
  if not p then
    return files
  end
  for entry in p:lines() do
    local candidate = dir .. "/" .. entry
    local stat = io.popen("test -f '" .. candidate .. "' && echo file\n")
    if stat then
      local result = stat:read("*l")
      stat:close()
      if result == "file" and (candidate:match("%.md$") or candidate:match("%.markdown$")) then
        table.insert(files, candidate)
      end
    end
  end
  table.sort(files)
  return files
end

local function read_include_file(resolved)
  local fh, err = io.open(resolved, "r")
  if not fh then
    io.stderr:write("[include] unable to read " .. resolved .. ": " .. (err or "") .. "\n")
    return nil
  end
  local contents = fh:read("*a")
  fh:close()
  return contents
end

local function expand_include_div(div)
  if not has_class(div, "include") then
    return nil
  end

  expand_compound_classes(div)
  local allowed = enforce_stage_visibility(div)
  if not allowed then
    return {}
  end

  local section_allowed = enforce_section_visibility(div)
  if not section_allowed then
    return {}
  end

  local attrs = div.attributes or {}
  local target = attrs.path
    or attrs.src
    or attrs.file
    or attrs.dir
    or attrs["data-dir"]
    or attrs["data-path"]
    or attrs["data-src"]
    or attrs["data-file"]
  if not target or target == "" then
    io.stderr:write("[include] missing path attribute on include block\n")
    return { pandoc.Para({ pandoc.Str("[include missing path]") }) }
  end

  local resolved = resolve_include_path(target)
  if not resolved then
    io.stderr:write("[include] unable to resolve path for " .. target .. "\n")
    return { pandoc.Para({ pandoc.Str("[include path error]") }) }
  end

  local include_targets = {}

  local attr_mode = attrs.mode
    or attrs["data-mode"]
    or ((attrs.dir or attrs["data-dir"]) and "dir")
    or "file"
  local separator_mode = "rule"
  local section_glyph = nil
  local raw_sep = attrs.separator or attrs.sep or attrs["data-separator"] or attrs["data-sep"]
  if raw_sep then
    local lowered = raw_sep:lower()
    if lowered == "none" or lowered == "false" or lowered == "off" then
      separator_mode = "none"
    end
  end
  local glyph_attr = attrs["glyph"] or attrs["section-glyph"] or attrs["heading-glyph"]
  if glyph_attr and glyph_attr ~= "" then
    section_glyph = glyph_attr
  end
  local banner_text = nil
  local banner_use_filename = false
  local raw_banner = attrs.banner
    or attrs["page-banner"]
    or attrs["running-head"]
    or attrs["runninghead"]
    or attrs["data-banner"]
    or attrs["data-running-head"]
  if raw_banner and raw_banner ~= "" then
    local trimmed = raw_banner:gsub("^%s+", ""):gsub("%s+$", "")
    if trimmed ~= "" then
      local lowered = trimmed:lower()
      if lowered == "filename" or lowered == "file" or lowered == "basename" or lowered == "auto" then
        banner_use_filename = true
      else
        banner_text = trimmed
      end
    end
  end

  local literal_mode = attr_mode == "literal"
    or attr_mode == "code"
    or has_class(div, "code")
    or has_class(div, "literal")
    or attr_truthy(attrs.literal)

  local is_dir = attr_mode == "dir" or resolved:sub(-1) == "/" or path_is_dir(resolved)
  local namespace_ids = is_dir
  local raw_namespace = attrs["namespace-ids"] or attrs["data-namespace-ids"]
  if raw_namespace ~= nil then
    namespace_ids = attr_truthy(raw_namespace)
  end

  if is_dir then
    local files = list_markdown_files(resolved:gsub("/$", ""))
    if #files == 0 then
      io.stderr:write("[include] no markdown files found in directory " .. resolved .. "\n")
      return { pandoc.Para({ pandoc.Str("[include empty directory]") }) }
    end
    include_targets = files
  else
    include_targets = { resolved }
  end

  local assembled = {}

  local total_targets = #include_targets
  for idx, include_path in ipairs(include_targets) do
    if include_stack[include_path] then
      io.stderr:write("[include] recursive include detected for " .. include_path .. "\n")
      table.insert(
        assembled,
        pandoc.Para({ pandoc.Str("[include recursion skipped: " .. include_path .. "]") })
      )
      goto continue
    end

    local contents = read_include_file(include_path)
    if not contents then
      goto continue
    end

    local inserted_blocks = false

    if literal_mode then
      table.insert(assembled, build_literal_code_block(contents, div, attrs))
      inserted_blocks = true
    else
      include_stack[include_path] = true
      local ok, included = pcall(function()
        return pandoc.read(contents, "markdown")
      end)
      include_stack[include_path] = nil

      if not ok then
        io.stderr:write("[include] failed to parse " .. include_path .. ": " .. tostring(included) .. "\n")
        goto continue
      end

      included.blocks = convert_shorthand_blocks(included.blocks)
      if section_glyph then
        apply_section_heading_glyph(included.blocks, section_glyph)
      end
      if namespace_ids then
        local file_base = basename_without_ext(include_path)
        local prefix = slugify_identifier_source(file_base)
        if prefix then
          included.blocks = namespace_header_identifiers(included.blocks, prefix, 3)
        end
      end
      for _, b in ipairs(included.blocks) do
        table.insert(assembled, b)
        inserted_blocks = true
      end
    end

    if inserted_blocks and separator_mode ~= "none" and idx < total_targets then
      table.insert(assembled, pandoc.HorizontalRule())
    end

    ::continue::
  end

  local final_banner_text = banner_text
  if not final_banner_text and banner_use_filename then
    final_banner_text = basename_without_ext(target)
      or basename_without_ext(resolved)
  end

  if final_banner_text and #assembled > 0 then
    local format_hint = FORMAT or ""
    if format_hint:match("latex") then
      local escaped = latex_escape_argument(final_banner_text)
      local starts_with_level_one = begins_with_level_one_header(assembled)
      local env_name = starts_with_level_one and "includepagebannerchapter" or "includepagebanner"
      local wrapped = { pandoc.RawBlock("latex", "\\begin{" .. env_name .. "}{" .. escaped .. "}\n") }
      for _, block in ipairs(assembled) do
        table.insert(wrapped, block)
      end
      table.insert(wrapped, pandoc.RawBlock("latex", "\\end{" .. env_name .. "}\n"))
      assembled = wrapped
    else
      local attr = pandoc.Attr("", { "include-banner" }, { ["data-banner-text"] = final_banner_text })
      local wrapper = pandoc.Div(assembled, attr)
      assembled = { wrapper }
    end
  end

  return assembled
end

-- ---------------------------------------------------------------------------
-- LaTeX/PDF aware block handlers
-- ---------------------------------------------------------------------------

local appendix_started = false
local first_chapter_seen = false

NOTE_VARIANTS = {
  "idea",
  "insight",
  "warning",
}

local function chapter_page_break_block(format_hint)
  format_hint = (format_hint or ""):lower()
  if format_hint == "" then
    return nil
  end

  if format_hint:match("latex") then
    return pandoc.RawBlock("latex", "\\clearpage")
  end

  if format_hint:match("docx") or format_hint:match("openxml") then
    return pandoc.RawBlock("openxml", "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>")
  end

  if format_hint:match("rtf") then
    return pandoc.RawBlock("rtf", "{\\pard\\page\\par}")
  end

  return nil
end

local function note_variant(div)
  if not div or not div.classes then
    return nil
  end

  -- Treat ::: note.insight.major as a distinct "insight-major" variant
  local has_insight = has_class(div, "insight")
  local has_major   = has_class(div, "major")

  if has_insight and has_major then
    return "insight-major"
  end

  -- Fallback: simple variants
  for _, candidate in ipairs(NOTE_VARIANTS) do
    if has_class(div, candidate) then
      return candidate
    end
  end

  return nil
end


local function inject_note_variant(div, variant)
  if not variant then
    return
  end

  -- note.idea: inline 💡 if possible, else neutral badge
  if variant == "idea" then
    local first = div.content[1]
    if first and first.t == "Para" and first.content then
      table.insert(first.content, 1,
        pandoc.RawInline("latex", "\\notevariantideainline{}")
      )
      return
    end
    table.insert(div.content, 1,
      pandoc.RawBlock("latex", "\\notevariant{idea}\n")
    )
    return
  end

  -- note.insight (minor): ornamental asterism row (⁂), not inline
  if variant == "insight" then
    table.insert(div.content, 1,
      pandoc.RawBlock("latex", "\\notevariantinsight\n")
    )
    return
  end

  -- note.insight.major (major): badge strip with ⁂
  if variant == "insight-major" then
    table.insert(div.content, 1,
      pandoc.RawBlock("latex", "\\notevariantinsightmajor\n")
    )
    return
  end

  -- note.warning and any other variants → generic badge
  table.insert(div.content, 1,
    pandoc.RawBlock("latex", "\\notevariant{" .. variant .. "}\n")
  )
end



local function handle_div(div)
  local semantics_changed = apply_semantic_aliases(div)
  local allowed, stage_changed = enforce_stage_visibility(div)
  if not allowed then
    return {}
  end
  local section_allowed, section_changed = enforce_section_visibility(div)
  if not section_allowed then
    return {}
  end

  local mutated = semantics_changed or stage_changed or section_changed

  div.attributes = div.attributes or {}

  local has_sidebar_semantics = has_epub_type(div.attributes, "aside") or has_epub_type(div.attributes, "sidebar")
  local has_inline_hint = has_epub_type(div.attributes, "sidebar-inline") or has_class(div, "sidebar-inline")
  local has_block_hint = has_class(div, "sidebar-block") or div.attributes["data-sidebar"] == "block"

  local is_sidebar_inline = has_inline_hint or (has_sidebar_semantics and not has_block_hint)
  if is_sidebar_inline and not has_inline_hint then
    add_epub_type_token(div.attributes, "sidebar-inline")
  end

  local is_sidebar_block = has_sidebar_semantics and not is_sidebar_inline

  local heading_decorated = false
  if is_sidebar_inline then
    if decorate_sidebar_heading(div.content) then
      mutated = true
      heading_decorated = true
    end
  end

  if is_sidebar_block then
    if insert_sidebar_badge(div) then
      mutated = true
    end
  elseif is_sidebar_inline and not heading_decorated then
    if inject_sidebar_inline_marker(div) then
      mutated = true
    end
  end

  if not FORMAT:match("latex") then
    return mutated and div or nil
  end

  if has_epub_type(div.attributes, "part") then
    return wrap_in_env(div, "parttitlepage")
  end

  if has_epub_type(div.attributes, "bridge") then
    return wrap_in_env(div, "bridgeheadblock")
  end

  if has_epub_type(div.attributes, "callout") then
    return wrap_in_env(div, "calloutbox")
  end

  if has_epub_type(div.attributes, "note") then
    local variant = note_variant(div)
    inject_note_variant(div, variant)
    local env = variant == "warning" and "noteboxwarning" or "notebox"
    return wrap_in_env(div, env)
  end

  if has_epub_type(div.attributes, "example") then
    return wrap_in_env(div, "examplebox")
  end

  if has_epub_type(div.attributes, "definition") then
    return wrap_in_env(div, "definitionbox")
  end

  if has_epub_type(div.attributes, "epigraph") then
    return wrap_in_env(div, "epigraph")
  end

  if has_epub_type(div.attributes, "epigraph-inline") then
    return wrap_in_env(div, "epigraphtight")
  end

  if is_sidebar_inline then
    return wrap_in_env(div, "sidebartight")
  end

  if has_sidebar_semantics then
    return wrap_in_env(div, "sidebar")
  end

  return mutated and div or nil
end

local function handle_header(h)
  local semantics_changed = apply_semantic_aliases(h)
  local allowed, stage_changed = enforce_stage_visibility(h)
  if not allowed then
    return {}
  end
  local section_allowed, section_changed = enforce_section_visibility(h)
  if not section_allowed then
    return {}
  end
  local role_scrubbed = scrub_header_role(h.attributes)
  local format_hint = (FORMAT or ""):lower()
  local wants_latex = format_hint:match("latex") ~= nil
  local wants_office_break = format_hint:match("docx")
    or format_hint:match("openxml")
    or format_hint:match("rtf")

  local has_chapter_semantics = has_epub_type(h.attributes, "chapter")
  local is_level_one_header = (h.level or 0) == 1

  local treat_as_chapter = false
  if wants_latex and has_chapter_semantics then
    treat_as_chapter = true
  elseif wants_office_break and (has_chapter_semantics or is_level_one_header) then
    treat_as_chapter = true
  end

  if treat_as_chapter then
    local out = {}
    if first_chapter_seen then
      local breaker = chapter_page_break_block(format_hint)
      if breaker then
        table.insert(out, breaker)
      end
    else
      first_chapter_seen = true
    end
    table.insert(out, h)
    return out
  end

  if not wants_latex then
    return (semantics_changed or role_scrubbed or stage_changed or section_changed) and h or nil
  end

  if has_epub_type(h.attributes, "appendix") then
    local out = {}
    if not appendix_started then
      appendix_started = true
      table.insert(out, pandoc.RawBlock("latex", "\\appendix"))
    end
    table.insert(out, h)
    return out
  end

  return (semantics_changed or role_scrubbed or stage_changed or section_changed) and h or nil
end

local function handle_span(span)
  local semantics_changed = apply_semantic_aliases(span)
  local allowed, stage_changed = enforce_stage_visibility(span)
  if not allowed then
    return {}
  end

  local section_allowed, section_changed = enforce_section_visibility(span)
  if not section_allowed then
    return {}
  end

  if semantics_changed or stage_changed or section_changed then
    return span
  end

  return nil
end

-- Helper used by the LaTeX sidebar post-processor
local function collect_sidebar_blocks(blocks, i)
  local collected = {}
  local h = blocks[i]
  local level = h.level or 0
  table.insert(collected, h)
  i = i + 1

  while i <= #blocks do
    local b = blocks[i]

    if b.t == "HorizontalRule" then
      i = i + 1
      break
    end

    if b.t == "Header" and b.level <= level then
      break
    end

    table.insert(collected, b)
    i = i + 1
  end

  return collected, i
end

local function latex_sidebar_wrapper(doc)
  if not FORMAT:match("latex") then
    return doc
  end

  local blocks = doc.blocks
  local out = {}
  local i = 1

  while i <= #blocks do
    local b = blocks[i]

    if b.t == "Header" then
      apply_semantic_aliases(b)

      if b.attributes and b.attributes["epub:type"] then
        local is_inline = has_epub_type(b.attributes, "sidebar-inline")
        if is_inline or has_epub_type(b.attributes, "aside") or has_epub_type(b.attributes, "sidebar") then
          if is_inline then
            inject_sidebar_glyph(b)
          end
          local collected
          collected, i = collect_sidebar_blocks(blocks, i)

          local env = is_inline and "sidebartight" or "sidebar"
          table.insert(out, pandoc.RawBlock("latex", "\\begin{" .. env .. "}"))
          if not is_inline then
            table.insert(out, pandoc.RawBlock("latex", "\\sidebarbadge"))
          end
          for _, cb in ipairs(collected) do
            table.insert(out, cb)
          end
          table.insert(out, pandoc.RawBlock("latex", "\\end{" .. env .. "}"))
          goto continue
        end
      end
    end

    table.insert(out, b)
    i = i + 1
    ::continue::
  end

  doc.blocks = out
  return doc
end

return {
  { Pandoc = preprocess_shorthand },
  { Div = expand_include_div },
  {
    Div = handle_div,
    Header = handle_header,
    Span = handle_span,
    Str = replace_meta_placeholders,
    Pandoc = latex_sidebar_wrapper
  }
}
