# Part and Series Naming Configuration

The TOC generator supports configurable part/series naming schemes. While the framework is opinionated about directory structure (using `parts/`, `chapters/`, `appendices/`, etc.), the *display labels* for major divisions can be customized to match your manuscript's conventions.

## Overview

Different manuscripts use different conventions for major divisions:

- **"Series A", "Series B", "Series C"...** (letter-based, used in this manuscript)
- **"Part One", "Part Two", "Part Three"...** (word-based numbers)
- **"Part 1", "Part 2", "Part 3"...** (numeric)
- **"Part I", "Part II", "Part III"...** (Roman numerals)
- **"Book One", "Book Two"...** (alternative prefix)

All of these can be configured via the `toc.parts` section in `iasp-config.yaml`.

------

## Configuration Reference

All settings live under `toc.parts` in your `iasp-config.yaml`:

```yaml
toc:
  parts:
    fallback_label: "Series {part_id}"
    id_from_filename_pattern: "SERIES\\s+([A-D])"
    code_pattern: "^([A-D])(\\d+)(?:[.\\-—|:]\\s*|\\s+)(.+)$"
    header_pattern: "^SERIES\\s+[A-D]\\s*[—\\-]\\s*PART\\s+\\d+"
```

### Settings

| Setting | Purpose | Default |
|---------|---------|---------|
| `fallback_label` | Template for TOC titles when no explicit `toc-title` is found | `"Part {part_id}"` |
| `id_from_filename_pattern` | Regex to extract part ID from filenames (case-insensitive) | `"SERIES\\s+([A-D])"` |
| `code_pattern` | Regex for parsing chapter codes; must have 3 capture groups | See below |
| `header_pattern` | Regex to identify part header lines to skip in outlines | See below |

### `fallback_label`

A template string used when a part file doesn't have an explicit `toc-title` attribute. Use `{part_id}` as a placeholder for the extracted identifier.

**Examples:**
- `"Series {part_id}"` → "Series A", "Series B"
- `"Part {part_id}"` → "Part 1", "Part I", "Part One"
- `"Book {part_id}"` → "Book 1", "Book One"

### `id_from_filename_pattern`

A regex pattern (case-insensitive) applied to filenames in the `parts/` directory to extract the part identifier. The first capture group becomes the `{part_id}`.

**Examples:**
- `"SERIES\\s+([A-D])"` matches `SERIES A Reclaiming Humanity.md` → captures `"A"`
- `"PART\\s+(\\d+)"` matches `Part 1 Introduction.md` → captures `"1"`
- `"PART\\s+([IVXLCDM]+)"` matches `Part II The Crisis.md` → captures `"II"`

### `code_pattern`

A regex for parsing chapter codes like "A1. Title" or "2.3 Subtitle". Must have **three capture groups**:

1. Part identifier (e.g., `"A"`, `"1"`, `"II"`)
2. Chapter/section number (e.g., `"1"`, `"2"`)
3. Title text

**Default (series-letter):**
```regex
^([A-D])(\d+)(?:[.\-—|:]\s*|\s+)(.+)$
```
Matches: `A1. The Beginning`, `B2 — The Middle`, `C3: The End`

### `header_pattern`

A regex to identify part header lines within chapter files. These lines are skipped when generating expanded outlines to avoid duplication.

**Default (series-letter):**
```regex
^SERIES\s+[A-D]\s*[—\-]\s*PART\s+\d+
```
Matches: `SERIES A — PART 1`, `SERIES B - PART 2`

------

## Example Configurations

### Series Letter (Default for This Manuscript)

```yaml
toc:
  parts:
    fallback_label: "Series {part_id}"
    id_from_filename_pattern: "SERIES\\s+([A-D])"
    code_pattern: "^([A-D])(\\d+)(?:[.\\-—|:]\\s*|\\s+)(.+)$"
    header_pattern: "^SERIES\\s+[A-D]\\s*[—\\-]\\s*PART\\s+\\d+"
```

**Expected filenames:** `SERIES A Reclaiming Humanity.md`, `SERIES B When Systems Fail.md`  
**Chapter codes:** `A1. Title`, `A2. Title`, `B1. Title`

### Numeric Parts (Part 1, Part 2...)

```yaml
toc:
  parts:
    fallback_label: "Part {part_id}"
    id_from_filename_pattern: "PART\\s+(\\d+)"
    code_pattern: "^(\\d+)[.](\\d+)(?:[.\\-—|:]\\s*|\\s+)(.+)$"
    header_pattern: "^PART\\s+\\d+"
```

**Expected filenames:** `Part 1 Introduction.md`, `Part 2 The Crisis.md`  
**Chapter codes:** `1.1 Title`, `1.2 Title`, `2.1 Title`

### Roman Numeral Parts (Part I, Part II...)

```yaml
toc:
  parts:
    fallback_label: "Part {part_id}"
    id_from_filename_pattern: "PART\\s+([IVXLCDM]+)"
    code_pattern: "^([IVXLCDM]+)[.](\\d+)(?:[.\\-—|:]\\s*|\\s+)(.+)$"
    header_pattern: "^PART\\s+[IVXLCDM]+"
```

**Expected filenames:** `Part I Introduction.md`, `Part II The Crisis.md`  
**Chapter codes:** `I.1 Title`, `I.2 Title`, `II.1 Title`

### Word-Based Parts (Part One, Part Two...)

```yaml
toc:
  parts:
    fallback_label: "Part {part_id}"
    id_from_filename_pattern: "PART\\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)"
    code_pattern: "^(One|Two|Three)[.](\\d+)(?:[.\\-—|:]\\s*|\\s+)(.+)$"
    header_pattern: "^PART\\s+(One|Two|Three|Four|Five)"
```

**Expected filenames:** `Part One Introduction.md`, `Part Two The Crisis.md`  
**Chapter codes:** `One.1 Title`, `Two.1 Title`

------

## Notes

- **Regex escaping:** In YAML, backslashes must be doubled (`\\s` instead of `\s`).
- **Case sensitivity:** The `id_from_filename_pattern` is applied case-insensitively.
- **Capture groups:** The `code_pattern` must always have exactly three capture groups.
- **Fallback behavior:** If a part file has an explicit `toc-title` attribute, the `fallback_label` is not used.
