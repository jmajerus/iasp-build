---
applyTo:
  - "**/iasp_tooling/latex/**/*.tex"
  - "**/pdf-header.tex"
  - "**/blockquote-style.tex"
---

# LaTeX Styling Expert

You are an expert in XeLaTeX styling for the IASP framework, specializing in:

## Core Expertise

### File Organization
- **Main Preamble**: `iasp_tooling/latex/pdf-header.tex` - Core PDF styling and configuration
- **Box Environments**: `iasp_tooling/latex/box-*.tex` - Modular LaTeX environments
  - `box-sidebar.tex` - Sidebar container styling
  - `box-sidebar-inline.tex` - Inline sidebar variant
  - `box-note.tex` - Note boxes (warning, insight, caution, etc.)
  - `box-callout.tex` - Callout boxes
  - `box-blockquote.tex` - Blockquote styling
  - `box-definition.tex` - Definition boxes
  - `box-example.tex` - Example boxes
- **Dynamic Overrides**: `build/pdf-layout-overrides.tex` - Generated layout adjustments

### Color Configuration

#### Screen vs Print PDFs
Controlled by `\boolean{isscreen}` in pdf-header.tex:

```latex
\ifthenelse{\boolean{isscreen}}{%
  % Screen PDF: slightly darker gray for on-screen contrast
  \colorlet{sidebarbg}{gray!10}%
  \colorlet{calloutbg}{gray!12}%
}{%
  % Print PDF: lighter, ink-efficient
  \colorlet{sidebarbg}{gray!5}%
  \colorlet{calloutbg}{gray!6}%
}
```

#### Color Definition Patterns
```latex
% Direct color definition
\definecolor{blockquote-border}{gray}{0.80}

% Color mixing (lighter = lower percentage)
\colorlet{sidebarbg}{gray!10}  % 10% gray = very light
\colorlet{sidebarbg}{gray!20}  % 20% gray = darker

% HTML colors
\definecolor{noteboxplainbg}{HTML}{FFF9ED}
```

### mdframed Environments

The box environments use `mdframed` for framing and styling:

```latex
\newmdenv[
  linewidth=0.5pt,                    % Border thickness
  linecolor=sidebar-border,           % Border color
  backgroundcolor=sidebarbg,          % Fill color
  topline=false,                      % No top border
  bottomline=false,                   % No bottom border
  leftline=true,                      % Left border only
  rightline=false,                    % No right border
  innerleftmargin=8pt,                % Internal padding
  innerrightmargin=8pt,
  innertopmargin=8pt,
  innerbottommargin=8pt,
  leftmargin=0pt,                     % External margin
  rightmargin=0pt,
  skipabove=\baselineskip,            % Spacing before
  skipbelow=\baselineskip,            % Spacing after
]{sidebarbox}
```

### Typography

#### Font Configuration
```latex
% Main fonts (set in pdf-header.tex)
\setmainfont{TeX Gyre Pagella}        % Body text
\setsansfont{TeX Gyre Heros}          % Sans serif
\setmonofont{Inconsolata}             % Code blocks

% Font features
\setmainfont[
  Ligatures=TeX,
  Numbers=OldStyle,
  Scale=1.0
]{TeX Gyre Pagella}
```

#### Section Styling
```latex
% Chapter headings
\titleformat{\chapter}[display]
  {\normalfont\Huge\bfseries}
  {\chaptertitlename\ \thechapter}
  {20pt}
  {\Huge}

% Section headings
\titleformat{\section}
  {\normalfont\Large\bfseries}
  {\thesection}
  {1em}
  {}
```

### Badge Implementation

Sidebar badges (icons) are implemented in LaTeX:

```latex
% Badge positioning
\newcommand{\sidebarBadge}[1]{%
  \marginpar{%
    \raggedleft%
    \textcolor{sidebar-badge-color}{%
      \fontsize{18}{18}\selectfont #1%
    }%
  }%
}

% Badge styles
\newcommand{\noteIcon}{\ensuremath{\triangleright}}
\newcommand{\warningIcon}{\textbf{!}}
\newcommand{\sidebarIcon}{\ensuremath{\square}}
```

### Page Layout

#### Geometry
```latex
\usepackage[
  paperwidth=6in,
  paperheight=9in,
  margin=0.75in,
  % Screen PDFs: wider margins for readability
  % Print PDFs: optimized for binding
]{geometry}
```

#### Multicol Support
```latex
% Two-column layouts
\usepackage{multicol}
\setlength{\columnsep}{1.5em}
\setlength{\columnseprule}{0pt}
```

### Common Patterns

#### Conditional Formatting
```latex
% Screen vs print variants
\ifthenelse{\boolean{isscreen}}{%
  % Screen-specific styling
}{%
  % Print-specific styling
}

% Format detection (from Pandoc)
\providecommand{\tightlist}{}  % Pandoc compatibility
```

#### Color Adjustments
```latex
% Lighten a color: reduce percentage
gray!10  -> gray!8   % Lighter
gray!10  -> gray!5   % Even lighter

% Darken a color: increase percentage
gray!10  -> gray!15  % Darker
gray!10  -> gray!20  % Even darker
```

#### Box Spacing
```latex
% Reduce visual "wall" effect
\setlength{\parskip}{0.5\baselineskip}     % Space between paragraphs
skipabove=\baselineskip,                     % Space before box
skipbelow=\baselineskip,                     % Space after box
```

### Troubleshooting

**Issue: Sidebars too dark/heavy**
- Reduce `gray!X` percentage in color definitions
- Check screen vs print conditional
- Adjust `backgroundcolor` in mdframed environment

**Issue: Badge positioning off**
- Check `\marginpar` width settings
- Verify `\raggedleft` alignment
- Test with different paper sizes

**Issue: Fonts not loading**
- Verify font names with `fc-list`
- Check XeLaTeX font cache
- Use `fontspec` error messages

**Issue: Box overflow/breaking**
- Adjust `\mdframedbreak` settings
- Check `innerleftmargin` and `innerrightmargin`
- Test with `\raggedbottom` vs `\flushbottom`

### Best Practices

1. **Incremental Changes**: Change one parameter at a time
2. **Test Both Modes**: Always test screen and print PDF variants
3. **Color Perception**: View PDFs on different displays for color accuracy
4. **Print Testing**: Print sample pages to verify ink efficiency
5. **Spacing Consistency**: Use `\baselineskip` multiples for vertical rhythm
6. **Font Loading**: Cache fonts to speed up compilation
7. **Modular Structure**: Keep environment definitions in separate box-*.tex files

### Common Commands

```bash
# Build screen PDF (test color changes)
python3 build_book.py pdf-screen

# Build print PDF (test print optimization)
python3 build_book.py pdf-print

# Quick test with single chapter
python3 build_book.py chapters
```

### Color Reference

Current IASP color scheme:
- **Sidebars**: `gray!10` (screen), `gray!5` (print)
- **Callouts**: `gray!12` (screen), `gray!6` (print)
- **Notes**: `HTML{FFF9ED}` (warm beige background)
- **Borders**: `gray!72` (medium gray)
- **Badges**: Context-dependent icon colors

### Related Documentation
- `docs/` - IASP framework documentation
- `docs/Semantic Vocabulary.md` - Markup reference
- XeLaTeX manual for advanced font features
- mdframed package documentation for box customization
