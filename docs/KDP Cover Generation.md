# KDP Cover Generation

Generate print-ready cover PDFs for Kindle Direct Publishing (KDP).

## Overview

The KDP cover generator creates a full "wraparound" cover PDF that includes:
- **Front cover** (right side)
- **Spine** (center strip)
- **Back cover** (left side)
- **Bleed margins** (0.125" on all outer edges, per KDP requirements)

The spine width is automatically calculated based on your book's page count and paper type.

---

## Quick Start

### 1. Prepare Your Cover Images

Create high-resolution cover images (300 DPI minimum):

```bash
mkdir -p assets/covers
# Add your cover images:
# - assets/covers/kdp-front.jpg (front cover)
# - assets/covers/kdp-back.jpg (back cover)
# - assets/covers/spine-graphic.jpg (optional spine image)
```

**Image Dimensions** (for 6×9" trim size @ 300 DPI):
- Front/Back: `1800 × 2700 pixels` (6" × 9")
- Spine: Varies by page count (typically `50-200 × 2700 pixels`)

### 2. Configure in `iasp-config.yaml`

```yaml
kdp:
  enabled: true
  trim_width: 6.0      # Book width in inches
  trim_height: 9.0     # Book height in inches
  paper_type: "white"  # Options: white, cream, color
  page_count: null     # Auto-detected from build/book.pdf
  
  front_cover: "assets/covers/kdp-front.jpg"
  back_cover: "assets/covers/kdp-back.jpg"
  spine_image: null   # Or path to spine graphic
  
  spine_text: "THE STRUGGLE AGAINST DEHUMANIZATION"
  spine_author: "MAJERUS"
```

### 3. Generate Cover

```bash
# Using build pipeline
python3 build_book.py kdp-cover

# Or directly
python3 iasp_tooling/scripts/generate_kdp_cover.py

# With CLI overrides
python3 iasp_tooling/scripts/generate_kdp_cover.py \
  --page-count 350 \
  --paper-type cream \
  --front-cover my-front.jpg
```

Output: `build/kdp-cover.pdf`

---

## Configuration Reference

### Trim Sizes

Common KDP trim sizes:

| Size | Description | Configuration |
|------|-------------|---------------|
| 6×9" | US Trade (most common) | `trim_width: 6.0, trim_height: 9.0` |
| 5.5×8.5" | Digest | `trim_width: 5.5, trim_height: 8.5` |
| 5×8" | Compact | `trim_width: 5.0, trim_height: 8.0` |
| 8.5×11" | US Letter | `trim_width: 8.5, trim_height: 11.0` |
| 6.14×9.21" | Royal | `trim_width: 6.14, trim_height: 9.21` |

### Paper Types

| Type | PPI | Spine Calculation | Best For |
|------|-----|-------------------|----------|
| `white` | 442 pages/inch | Thinnest spine | Most books |
| `cream` | 392 pages/inch | Thicker spine | Traditional novels |
| `color` | 444 pages/inch | Similar to white | Color interiors |

**Spine Width Examples** (for 300-page book):
- White: 0.68 inches
- Cream: 0.77 inches
- Color: 0.68 inches

### Cover Assets

#### Front/Back Covers
- **Resolution**: 300 DPI minimum (KDP requirement)
- **Dimensions**: Match trim size exactly
  - Example (6×9"): 1800×2700 pixels @ 300 DPI
- **Format**: JPG, PNG, or TIFF
- **Bleed**: Images are automatically positioned with bleed

#### Spine Image
- **Width**: Varies by page count (auto-calculated)
- **Height**: Must match trim height
- **Orientation**: Vertical (will appear on spine)
- **Optional**: If not provided, spine generated from `spine_text`

**Note**: Spines narrower than 0.25" (`~125px @ 300 DPI`) may not display text legibly. For thin books (<55 pages), consider omitting spine text.

---

## Workflow Integration

### Typical Workflow

```bash
# 1. Build your PDF to get accurate page count
python3 build_book.py pdf-print

# 2. Generate KDP cover (auto-detects page count from build/book.pdf)
python3 build_book.py kdp-cover

# 3. Review generated cover
xdg-open build/kdp-cover.pdf

# 4. Upload to KDP
# - Log in to kdp.amazon.com
# - Use "Cover Creator" or "Upload Your Cover"
# - Upload build/kdp-cover.pdf
# - KDP will validate spine width matches page count
```

### Advanced Options

```bash
# Force specific page count (override auto-detection)
python3 iasp_tooling/scripts/generate_kdp_cover.py --page-count 425

# Use cream paper
python3 iasp_tooling/scripts/generate_kdp_cover.py --paper-type cream

# Custom output path
python3 iasp_tooling/scripts/generate_kdp_cover.py --output build/my-cover.pdf

# Use specific cover images
python3 iasp_tooling/scripts/generate_kdp_cover.py \
  --front-cover assets/front-v2.jpg \
  --back-cover assets/back-v2.jpg \
  --spine-image assets/spine-art.png
```

---

## KDP Requirements Checklist

The generated cover PDF meets these KDP requirements:

- ✅ **PDF format** with embedded fonts (PDF/X-1a:2001 compatible)
- ✅ **300 DPI minimum** resolution
- ✅ **Correct dimensions** including 0.125" bleed
- ✅ **Spine width** calculated from page count and paper type
- ✅ **RGB color space** (converted to CMYK by KDP during processing)
- ✅ **Single-page PDF** (wraparound layout)

---

## Troubleshooting

### "Spine Width Doesn't Match"

KDP rejects covers if spine width doesn't match page count.

**Solution**:
1. Build your final PDF: `python3 build_book.py pdf-print`
2. Count pages in PDF (or let script auto-detect)
3. Regenerate cover: `python3 build_book.py kdp-cover`
4. Verify in KDP Cover Creator before finalizing

### Cover Images Don't Fit

Ensure your images match trim dimensions exactly:
- 6×9" trim → 1800×2700 px @ 300 DPI
- 5.5×8.5" trim → 1650×2550 px @ 300 DPI

### Spine Text Not Showing

For books under 55 pages (spine < 0.25"):
- Text won't fit legibly on spine
- Use `spine_image: null` and no `spine_text`
- Leave spine blank or use subtle pattern

### Low Resolution Warning

KDP requires 300 DPI minimum:
- Check your source images are high-resolution
- Verify `dpi: 300` in config (default)
- Don't reduce quality when exporting images

---

## Design Tips

### Front Cover
- Title clearly legible in thumbnail (1-inch size)
- Author name prominent
- Use high-contrast colors for readability
- Leave 0.25" safety margin from edges

### Back Cover
- ISBN barcode area: 2"×1.2" in bottom-right corner
- Brief description or blurb
- Author bio (optional)
- Publisher info/website
- Safe zone: 0.25" from all edges

### Spine
- Title reads from top to bottom (standard)
- Author name below title (if room)
- Publisher logo (optional, for thick books only)
- Minimum spine width for text: 0.25" (≥55 pages white paper)

### Color Considerations
- RGB images are automatically converted by KDP
- Avoid pure black (#000000) - use rich black
- Test print to verify colors before ordering

---

## Related Configuration

See also:
- [`iasp-config.yaml`](../../iasp-config.yaml) - KDP section
- [`metadata.yaml`](../../metadata.yaml) - Book metadata (title, author)
- [Build Pipeline](Build%20Pipeline.md) - Integration with other builds

---

## Resources

- [KDP Cover Templates](https://kdp.amazon.com/en_US/cover-templates) - Official calculator
- [KDP Cover Creator](https://kdp.amazon.com/en_US/help/topic/G201953020) - Online tool
- [Print Specifications](https://kdp.amazon.com/en_US/help/topic/G201834230) - Full requirements

---

## Future Enhancements

Planned improvements:
- [ ] Rotated spine text rendering
- [ ] ISBN barcode generation and positioning
- [ ] PDF/X-1a:2001 compliance validation
- [ ] Template-based cover generation
- [ ] Safety guide visualization
- [ ] Multiple profile support (hardcover, different trims)
