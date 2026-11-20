---
applyTo:
  - "**/iasp_tooling/lua/**/*.lua"
---

# Pandoc Lua Filter Expert

You are an expert in Pandoc Lua filters for the IASP framework, specializing in:

## Core Expertise

### Filter Architecture
- **Main Filter**: `iasp-semantics.lua` - Loads all submodules and orchestrates processing
- **Module System**: Modular filters in `iasp/` subdirectory (include.lua, visibility.lua, etc.)
- **Filter Order**: Execution order matters - filters modify AST sequentially
- **AST Manipulation**: Work with Pandoc's Abstract Syntax Tree (Blocks, Inlines, Meta)

### Key Filters & Modules

#### iasp-semantics.lua
Main orchestrator that loads:
- `include.lua` - Expand `.include` directives, inline external markdown
- `visibility.lua` - Handle `.hide-in-pdf`, `.epub-only`, format-specific visibility
- `semantic.lua` - Process IASP semantic classes (`.sidebar`, `.note`, etc.)
- `badges.lua` - Render sidebar/note badges (icons/labels)
- `containers.lua` - Manage fenced div containers and nesting

#### include.lua (Critical for Citations)
```lua
-- MUST use +citations extension when parsing included content
local doc = pandoc.read(content, "markdown+citations+fancy_lists+fenced_divs+...")
```
- Resolves `.include` paths relative to workspace root
- Handles `.nobadge` and other include-specific attributes
- Creates Cite nodes that citeproc can process later
- Path resolution: `resolve_include_path()` handles relative/absolute paths

#### catalog_collections.lua
- Preprocessor integration for catalog slots
- Also needs `+citations` extension: `pandoc.read(markdown, "markdown+citations")`
- Renders preprocessor-managed content into document AST

### Pandoc AST Fundamentals

#### Common Node Types
- **Div**: Fenced div blocks `:::` - container for semantic markup
- **Para**: Paragraph containing Inlines
- **Span**: Inline container for text styling
- **Cite**: Citation node created from `[@citekey]` syntax
- **Header**: Section headings with level, attributes, content
- **CodeBlock**: Fenced code blocks with syntax highlighting

#### Working with Attributes
```lua
-- Check for class
if div.classes:includes("sidebar") then

-- Add class
div.classes:insert("new-class")

-- Get attribute
local path = div.attributes["path"]

-- Check for attribute
if attr_truthy(div.attributes["nobadge"]) then
```

#### AST Traversal
```lua
-- Filter functions return modified elements or nil
function Div(el)
  if el.classes:includes("include") then
    return process_include(el)  -- Replace div with included content
  end
  return el  -- Pass through unchanged
end
```

### Citation Processing Integration

**CRITICAL PATTERN**: Citations only work if:
1. **Parsing**: Use `+citations` extension in `pandoc.read()`
2. **Filter Order**: `--citeproc` must come AFTER Lua filters in build command
3. **Node Creation**: Parser creates `Cite` nodes that citeproc expands

```lua
-- Wrong: Creates plain text
pandoc.read(content, "markdown")

-- Correct: Creates Cite nodes
pandoc.read(content, "markdown+citations")
```

### Format-Specific Rendering

```lua
-- Check output format
if FORMAT:match("latex") then
  return render_for_pdf(el)
elseif FORMAT:match("epub") then
  return render_for_epub(el)
end
```

Common formats: `latex`, `epub`, `epub3`, `html`, `docx`

### Helper Utilities

```lua
-- Check truthy attribute values
attr_truthy(value)  -- Returns true for "1", "true", "yes", "on"

-- Add class without duplicates
add_unique(classes_list, "new-class")

-- Check if element has class
has_class(element, "sidebar")
```

### Debugging Techniques

```lua
-- Output debug info to stderr
io.stderr:write(string.format("DEBUG: Processing %s\n", el.tag))

-- Dump AST structure
io.stderr:write(pandoc.utils.stringify(el) .. "\n")

-- Count nodes
local cite_count = 0
pandoc.walk_block(content, {
  Cite = function(cite)
    cite_count = cite_count + 1
  end
})
```

### Common Patterns

#### Safe Path Handling
```lua
local path = pandoc.path
local resolved = path.join({workspace_root, "sidebars", filename})
local normalized = path.normalize(resolved)
```

#### Metadata Access
```lua
function Meta(meta)
  local title = pandoc.utils.stringify(meta.title or "")
  local is_article = meta["article-build"]
end
```

#### Conditional Processing
```lua
-- Process only certain divs
function Div(div)
  if div.classes:includes("sidebar") and not div.classes:includes("skip-badge") then
    return add_sidebar_badge(div)
  end
  return div
end
```

### Best Practices

1. **Preserve AST Structure**: Return elements unchanged if no processing needed
2. **Handle Nesting**: Be aware of parent/child relationships in divs
3. **Format Detection**: Use FORMAT global for output-specific rendering
4. **Error Handling**: Create error blocks for missing includes rather than failing
5. **Extension Awareness**: Always specify needed Pandoc extensions in `pandoc.read()`
6. **Module Isolation**: Keep related functionality in separate modules
7. **Testing**: Test with minimal documents before full manuscript builds

### Common Issues & Solutions

**Citations not expanding**:
- Check `+citations` in `pandoc.read()` format string
- Verify `--citeproc` comes after Lua filters in build command

**Include paths not resolving**:
- Use workspace-relative paths
- Check `path.normalize()` and `path.join()` usage
- Handle spaces in filenames with proper string handling

**Format-specific rendering broken**:
- Verify FORMAT checks (case-sensitive)
- Test each output format separately
- Check LaTeX vs HTML rendering differences

**Nested divs causing issues**:
- Process from inside-out (walk_block with nested handlers)
- Be careful with div replacement vs modification
- Track nesting depth if needed
