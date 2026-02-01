local M = {}

local function count_table_rows(table_block)
  if not table_block or table_block.t ~= "Table" then
    return 0
  end

  local count = 0
  local head = table_block.head
  if head and head.rows then
    count = count + #head.rows
  end
  local bodies = table_block.bodies
  if bodies then
    for _, body in ipairs(bodies) do
      if body.rows then
        count = count + #body.rows
      end
    end
  end
  local foot = table_block.foot
  if foot and foot.rows then
    count = count + #foot.rows
  end

  return count
end

local function count_table_columns(table_block)
  if not table_block or table_block.t ~= "Table" then
    return 0
  end

  if table_block.colspecs then
    return #table_block.colspecs
  end

  local c = table_block.c
  if type(c) == "table" and type(c[2]) == "table" then
    return #c[2]
  end

  return 0
end

function M.div_table_row_count(div)
  if not div or not div.content then
    return 0
  end
  local total = 0
  for _, block in ipairs(div.content) do
    if block.t == "Table" then
      total = total + count_table_rows(block)
    end
  end
  return total
end

function M.div_table_column_count(div)
  if not div or not div.content then
    return 0
  end
  local max_cols = 0
  for _, block in ipairs(div.content) do
    if block.t == "Table" then
      local cols = count_table_columns(block)
      if cols > max_cols then
        max_cols = cols
      end
    end
  end
  return max_cols
end

function M.create(opts)
  local function apply_table_appearance(div, format_hint)
    if not div or not div.content then
      return false
    end

    local wants_compact = opts.has_class(div, "table-compact")
    local wants_striped = opts.has_class(div, "table-striped")
    local wants_bordered = opts.has_class(div, "table-bordered")

    if not (wants_compact or wants_striped or wants_bordered) then
      return false
    end

    if not format_hint:match("latex") then
      return false
    end

    local updated = false
    local next_blocks = {}

    for _, block in ipairs(div.content) do
      if block.t == "Table" then
        if wants_compact then
          table.insert(next_blocks, pandoc.RawBlock("latex", "\\iaspTableCompactStart\n"))
        end
        if wants_bordered then
          table.insert(next_blocks, pandoc.RawBlock("latex", "\\begin{iaspTableBordered}\n"))
        end
        if wants_striped then
          table.insert(next_blocks, pandoc.RawBlock("latex", "\\iaspTableStripedStart\n"))
        end

        table.insert(next_blocks, block)

        if wants_striped then
          table.insert(next_blocks, pandoc.RawBlock("latex", "\\iaspTableStripedEnd\n"))
        end
        if wants_bordered then
          table.insert(next_blocks, pandoc.RawBlock("latex", "\\end{iaspTableBordered}\n"))
        end
        if wants_compact then
          table.insert(next_blocks, pandoc.RawBlock("latex", "\\iaspTableCompactEnd\n"))
        end
        updated = true
      else
        table.insert(next_blocks, block)
      end
    end

    if updated then
      div.content = next_blocks
    end

    return updated
  end

  local function apply_table_layout(div, format_hint, has_fullpage_layout, mutated)
    local has_table_semantics = opts.has_class(div, "table")

    if has_table_semantics and not has_fullpage_layout then
      local min_rows = opts.table_fullpage_min_rows()
      if min_rows and min_rows > 0 then
        local table_rows = M.div_table_row_count(div)
        if table_rows >= min_rows then
          opts.add_unique(div.classes, "layout-fullpage")
          opts.add_unique(div.classes, "table-fullpage")
          has_fullpage_layout = true
          mutated = true
        end
      end
    elseif has_table_semantics and has_fullpage_layout then
      opts.add_unique(div.classes, "table-fullpage")
    end

    if has_table_semantics and not opts.has_class(div, "table-compact") then
      local min_cols = opts.table_compact_min_cols()
      if min_cols and min_cols > 0 then
        local columns = M.div_table_column_count(div)
        if columns >= min_cols then
          opts.add_unique(div.classes, "table-compact")
          mutated = true
        end
      end
    end

    if has_table_semantics then
      if apply_table_appearance(div, format_hint) then
        mutated = true
      end
    end

    return has_fullpage_layout, mutated
  end

  return {
    apply_table_layout = apply_table_layout,
  }
end

return M
