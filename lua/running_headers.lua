-- running_headers.lua
-- Inject format-specific running head overrides when a block carries
-- the `data-running-head` attribute. This lets individual chapters or
-- front-matter inserts force a specific label such as "Table of Contents".

local function has_text(value)
  return value and value:match("%S") ~= nil
end

local function latex_escape(text)
  local replacements = {
    ["\\"] = "\\textbackslash{}",
    ["{"] = "\\{",
    ["}"] = "\\}",
    ["$"] = "\\$",
    ["&"] = "\\&",
    ["#"] = "\\#",
    ["%"] = "\\%",
    ["_"] = "\\_",
    ["~"] = "\\textasciitilde{}",
    ["^"] = "\\^{}",
  }
  return (text:gsub(".", function(ch)
    return replacements[ch] or ch
  end))
end

local function inject_running_head(blocks, label)
  local inserted = false

  if FORMAT:match("latex") then
    local escaped = latex_escape(label)
    local set_now = string.format("\\iaspSetRunningHeadNow{%s}", escaped)

    local header_index = 1
    for idx, block in ipairs(blocks) do
      if block.t == "Header" then
        header_index = idx
        break
      end
    end

    table.insert(blocks, header_index + 1, pandoc.RawBlock("latex", set_now))
    inserted = true
  end

  return inserted
end

return {
  {
    Div = function(div)
      if not div or not div.attributes then
        return nil
      end

      local label = div.attributes["data-running-head"]
      if not has_text(label) then
        return nil
      end

      local inserted = inject_running_head(div.content, label)
      if inserted then
        div.attributes["data-running-head"] = nil
        return div
      end

      return nil
    end,
  },
}
