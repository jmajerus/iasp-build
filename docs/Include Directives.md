# Include Directives

The `.include` fenced div allows chapters and appendices to pull in external Markdown fragments at build time.

---

## Basic Usage

```markdown
::: {.include path="subchapters/w1-background.md"}
:::
```

The Lua filter reads the referenced file, parses it, and splices the resulting blocks into the document before any other semantic processing. Wrappers like `::: sidebar` inside the included file behave exactly as if written inline.

---

## Attributes

### File Include

| Attribute | Aliases | Description |
|-----------|---------|-------------|
| `path` | `file`, `src` | Project-root–relative path to the Markdown file |

```markdown
::: {.include path="sidebars/ethics-note.md"}
:::
```

### Directory Include

| Attribute | Aliases | Description |
|-----------|---------|-------------|
| `dir` | `data-dir` | Path to a directory; includes all `.md`/`.markdown` files alphabetically |
| `mode` | — | Set to `"dir"` when using `path` for a directory |

```markdown
::: {.include dir="subchapters/w-series"}
:::

::: {.include path="subchapters/w-series" mode="dir"}
:::
```

### Separators

Directory includes drop a horizontal rule between files by default.

| Attribute | Values | Description |
|-----------|--------|-------------|
| `separator` | `"none"`, `"hr"` (default) | Control separator between files |
| `sep` | (alias) | Short form |

```markdown
::: {.include dir="patterns" separator="none"}
:::
```

---

## Glyphs and Banners

### Heading Glyphs

Prepend a glyph to every heading inside included fragments:

```markdown
::: {.include dir="cases" glyph="✶"}
:::
```

EPUB/HTML renders via `.section-heading-glyph` span; PDF uses `\sectionheadingglyph{…}`.

### Page Banners

Draw a gray bar across the top margin of PDF pages:

| Attribute | Aliases | Description |
|-----------|---------|-------------|
| `banner` | `page-banner`, `running-head` | Banner text or special value |

```markdown
::: {.include path="memos/internal.md" banner="Case Study – Internal Memos"}
:::
```

Special values for `banner`:
- `"filename"`, `"file"`, `"basename"`, `"auto"` — Use the file/directory name

EPUB/HTML wraps content in `.include-banner` div with `data-banner-text` attribute.

---

## List Mode

Emit a list of matched files instead of their contents:

| Attribute | Values | Description |
|-----------|--------|-------------|
| `list` | `"names"`, `"filenames"`, `"basename"` | Output as list |
| `list-style` | `"ordered"`, `"unordered"` | Numbered or bulleted |

```markdown
::: {.include dir="patterns" list="names" list-style="ordered"}
:::
```

Useful for appendix indexes that summarize available fragments.

---

## Literal and Code Modes

Include raw file contents as a code block:

| Attribute | Values | Description |
|-----------|--------|-------------|
| `mode` | `"literal"`, `"code"` | Raw inclusion |
| `lang` | language name | Syntax highlighting |

```markdown
::: {.include path="scripts/example.py" mode="code" lang="python"}
:::
```

---

## Important Notes

1. **Syntax**: Always use `{.include ...}` braces on the opener so Pandoc parses it as a Div.
2. **Recursion**: Recursive includes are blocked; missing files raise warnings.
3. **Paths**: Relative to project root; absolute paths also work.

---

## Use Cases

- **Appendix W-style modularity** — Split large appendices into subchapter files
- **Shared sidebars** — Store in `sidebars/` and include where needed
- **Pattern catalogs** — Directory includes with glyphs for consistent styling
- **Source listings** — Code mode for embedding scripts in technical annexes
