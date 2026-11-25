-- references_running_head.lua
-- Give the citeproc reference section its own running head in PDF output.
--
-- This filter must run AFTER --citeproc. Citeproc creates the reference
-- section (an unnumbered Header followed by Div#refs) only once the Lua
-- filters before it have finished, so running_headers.lua never sees it.
-- And because the heading is unnumbered, LaTeX typesets it with \chapter*,
-- which never calls \chaptermark. Without this filter the running head of
-- the reference pages keeps the title of the last chapter or appendix.

local function set_head_block(label)
  -- Guarded so documents built without pdf-header.tex still compile.
  return pandoc.RawBlock(
    "latex",
    string.format(
      "\\ifdefined\\iaspSetRunningHeadNow\\iaspSetRunningHeadNow{%s}\\fi",
      label
    )
  )
end

local function heading_label(header)
  -- Render the heading inlines as LaTeX so markup and special characters
  -- in a custom reference-section-title come through escaped.
  local doc = pandoc.Pandoc({ pandoc.Plain(header.content) })
  local latex = pandoc.write(doc, "latex")
  return (latex:gsub("%s+$", ""))
end

local function is_refs_div(block)
  return block and block.t == "Div" and block.identifier == "refs"
end

function Pandoc(doc)
  if not FORMAT:match("latex") then
    return nil
  end

  local blocks = doc.blocks
  for idx, block in ipairs(blocks) do
    if is_refs_div(block) then
      local header = blocks[idx - 1]
      if header and header.t == "Header" then
        -- Citeproc placed the heading (reference-section-title) before the div.
        blocks:insert(idx, set_head_block(heading_label(header)))
        return doc
      end

      -- An author-supplied ::: {#refs} may carry its own heading inside.
      local inner = block.content[1]
      if inner and inner.t == "Header" then
        block.content:insert(2, set_head_block(heading_label(inner)))
        return doc
      end

      return nil
    end
  end

  return nil
end
