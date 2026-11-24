# IASP Core

## Informative Authoring Semantics Profile — Core (Pandoc-friendly, compositional)

**Status:** Informative (non-normative)
 **Audience:** Authors and collaborators working on complex long-form nonfiction
 **Scope:** Authoring intent only (not rendering, markup, or standards compliance)

------

## 1. What IASP Is For

IASP gives authors **names for what their text is doing**.

Not how it is formatted.
 Not how it is encoded.
 Not how it is rendered.

IASP is a **thinking aid** that happens to be machine-friendly — not the other way around.

------

## 2. What IASP Is Not

IASP is **not**:

- a markup language
- a publishing standard
- a compliance checklist
- a validation system
- a style guide that enforces uniformity

Nothing in IASP is required.
 Nothing is “invalid” if unused.

------

## 3. Core Philosophy: Intent Is Layered

A passage may be:

- structurally a sidebar
- functionally an example
- tonally a warning

All at once.

IASP assumes **authorial intent is layered**, and supports naming those layers explicitly.

------

## 4. Compositional Semantics (Central Concept)

IASP terms are **composable**.

A simple convention expresses layered intent:

```
delivery.modifier
```

### Examples

- `note.insight`
   → “This is a note, and what it contributes is an insight.”
- `sidebar.example`
   → “This is optional to the main flow, and it functions as an example.”
- `footnote.counterpoint`
   → “This is ancillary, but it introduces an alternative view.”

### Interpretation (informative)

- The **leftmost term** names the *delivery role*
- Subsequent terms **qualify intent**

Composition expresses contextual meaning, not taxonomy.

`note.insight` does **not** mean “insight is a subtype of note.”
 It means “this note functions as an insight here.”

------

## 5. Two Axes of Meaning

IASP Core uses two axes:

### Axis A — Delivery Roles

“How does this text relate to the surrounding narrative flow?”

### Axis B — Modifiers

“What kind of work is this passage doing, and what stance is it signaling?”

These axes are intentionally **not** mutually exclusive.

------

## 6. Delivery Roles (Axis A)

Delivery roles describe placement and relationship to the main flow.

| Term           | Description                                                  |
| -------------- | ------------------------------------------------------------ |
| `front-matter` | Material framing the work (preface, intro, etc.)             |
| `series`       | Optional super-division above parts (use only if helpful)    |
| `part`         | Major thematic division                                      |
| `chapter`      | Primary unit of argument                                     |
| `section`      | Subdivision within a chapter                                 |
| `interlude`    | Intentional pause or tonal shift                             |
| `bridge`       | Transitional connective text                                 |
| `sidebar`      | Optional digression or parallel track                        |
| `note`         | Ancillary content tied to a point, but not necessarily a formal footnote |
| `footnote`     | Localized ancillary content                                  |
| `endnotes`     | Deferred ancillary content                                   |
| `appendix`     | Material outside the main narrative flow                     |

**Optionality:** Unmarked text is assumed to be part of the main flow.

------

## 7. Modifiers (Axis B)

Modifiers describe rhetorical function, reader guidance, or epistemic stance.

### 7.1 Argument and reasoning

| Term            | Description                         |
| --------------- | ----------------------------------- |
| `thesis`        | Central claim                       |
| `claim`         | Supporting assertion                |
| `counterpoint`  | Alternative or opposing view        |
| `qualification` | Limitation or nuance                |
| `implication`   | Consequence of an argument          |
| `synthesis`     | Integration of ideas                |
| `reflection`    | Interpretive or contemplative pause |
| `provocation`   | Intentionally unsettling prompt     |

### 7.2 Exposition and support

| Term         | Description                        |
| ------------ | ---------------------------------- |
| `example`    | Concrete illustration              |
| `case-study` | Extended real-world instance       |
| `background` | Contextual grounding               |
| `definition` | Clarification of a term            |
| `gloss`      | Brief explanatory note             |
| `analogy`    | Comparative explanation            |
| `insight`    | Moment of realization or reframing |

### 7.3 Reader signals and stance

| Term          | Description                   |
| ------------- | ----------------------------- |
| `warning`     | Risk, harm, or moral alert    |
| `notice`      | Important framing information |
| `caution`     | Advice against overreach      |
| `assumption`  | Declared premise              |
| `limitation`  | Known constraint              |
| `uncertainty` | Epistemic humility            |

------

## 8. Composition in Practice

Composition is **optional** and **situational**.

Common patterns:

- `sidebar.example`
- `sidebar.background`
- `note.insight`
- `note.breadcrumb`
- `note.definition`
- `footnote.source-note` *(if defined by an extension)*
- `bridge.reflection`
- `section.thesis` *(only if you find it useful to mark major moves)*

### Soft guidance (not rules)

- One **delivery role** is usually sufficient
- One or two **modifiers** are usually enough
- Over-tagging can substitute for clarity in prose — use judgment

IASP exists to support thinking, not replace writing.

------

## 9. Pandoc-Friendly Authoring (Informative)

IASP is designed to map cleanly onto common Pandoc authoring patterns:

- **Fenced divisions** with classes (e.g., `::: sidebar.example … :::`)
- **Heading attributes** (e.g., `### Title {.sidebar .insight}`)
- **File-level organization** (directories like `parts/`, `chapters/`, `sidebars/`)

IASP does not require any particular syntax; it only defines intent vocabulary.

------

## 10. Silence Is Allowed

IASP does not require that all passages be labeled.

Choosing not to tag intent is a valid authorial decision.

------

## 11. Relationship to Tooling (Informative)

Tools may choose to:

- map delivery roles to structural elements
- map modifiers to metadata or styling hooks
- preserve composed roles for search, analysis, or collaboration
- ignore roles entirely

IASP makes no requirements of tooling.

Build-control classes are not intent markup. They decide *whether* content appears in a given build, not what it means: `.draft` / `.final` choose by build stage, and `.profile-only` / `.standalone-only` choose by build profile. The reference tooling documents them under *Build Pipeline → Profile-Conditional Content*.

------

## 12. Why This Is Shareable

IASP supports shared authorship because it:

- names common authorial intuitions
- avoids format lock-in
- supports partial adoption
- permits different writing styles
- improves collaboration by clarifying intent

------

## 13. Status and Evolution

IASP Core is intentionally:

- incomplete
- extensible
- open to domain-specific extensions

New terms should be added when authors need them.

------

## Closing Note

> *Complex writing benefits from having names for complexity.*

IASP does not tell authors how to write.
 It gives them a language for understanding what they are already doing.

That is its only ambition — and its entire purpose.