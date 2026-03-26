#!/usr/bin/env python3
"""
generate_kdp_cover.py

Generate a KDP-compliant print cover PDF from front/back/spine images.

KDP Requirements:
- Full wraparound PDF (front + spine + back + bleed)
- Spine width calculated from page count and paper type
- PDF/X standard for print compliance
- 0.125" bleed on all outer edges

Usage:
    python3 generate_kdp_cover.py [--profile PROFILE]
    python3 generate_kdp_cover.py --page-count 350 --paper-type white
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import sys
import argparse
from typing import Literal

# Add repo root to path for IASP imports
# Script is at: repo/iasp_tooling/scripts/generate_kdp_cover.py
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from iasp_tooling.lib.config import load_config

ROOT = REPO_ROOT


# KDP spine width calculations (in inches)
# Based on KDP's official spine calculator
# https://kdp.amazon.com/en_US/cover-templates

def calculate_spine_width(
    page_count: int,
    paper_type: Literal["white", "cream", "color"] = "white"
) -> float:
    """Calculate spine width in inches based on page count and paper type.
    
    KDP paper thickness (pages per inch):
    - White: 442 PPI (0.002262 inches per page)
    - Cream: 392 PPI (0.002551 inches per page)
    - Color (standard): 444 PPI (0.002252 inches per page)
    """
    ppi_map = {
        "white": 442,
        "cream": 392,
        "color": 444,
    }
    
    ppi = ppi_map.get(paper_type, 442)
    spine_inches = page_count / ppi
    
    # KDP minimum spine width is 0.06"
    return max(0.06, spine_inches)


def get_kdp_dimensions(
    trim_width: float,
    trim_height: float,
    spine_width: float,
    bleed: float = 0.125
) -> tuple[float, float]:
    """Calculate full cover dimensions including bleed.
    
    Args:
        trim_width: Book trim width in inches
        trim_height: Book trim height in inches  
        spine_width: Calculated spine width in inches
        bleed: Bleed margin in inches (KDP standard is 0.125")
        
    Returns:
        (total_width, total_height) in inches
    """
    # Full width = front + spine + back + 2*bleed
    total_width = (trim_width * 2) + spine_width + (bleed * 2)
    
    # Full height = trim height + 2*bleed
    total_height = trim_height + (bleed * 2)
    
    return (total_width, total_height)


def create_kdp_cover(
    front_cover_path: Path | None,
    back_cover_path: Path | None,
    spine_image_path: Path | None,
    output_path: Path,
    trim_width: float,
    trim_height: float,
    page_count: int,
    paper_type: str = "white",
    dpi: int = 300,
    spine_text: str | None = None,
    spine_author: str | None = None,
) -> None:
    """Generate a KDP-compliant cover PDF.
    
    Args:
        front_cover_path: Path to front cover image (or None for placeholder)
        back_cover_path: Path to back cover image (or None for placeholder)
        spine_image_path: Path to spine graphic (or None to generate from text)
        output_path: Where to save the output PDF
        trim_width: Book trim width in inches (e.g., 6.0)
        trim_height: Book trim height in inches (e.g., 9.0)
        page_count: Total page count (for spine width calculation)
        paper_type: "white", "cream", or "color"
        dpi: Output resolution (KDP requires 300 DPI minimum)
        spine_text: Title text for spine (if no spine_image provided)
        spine_author: Author text for spine (optional)
    """
    # Calculate dimensions
    spine_width = calculate_spine_width(page_count, paper_type)
    bleed = 0.125  # KDP standard
    
    cover_width, cover_height = get_kdp_dimensions(
        trim_width, trim_height, spine_width, bleed
    )
    
    # Convert to pixels
    px_width = int(cover_width * dpi)
    px_height = int(cover_height * dpi)
    px_bleed = int(bleed * dpi)
    px_trim_width = int(trim_width * dpi)
    px_trim_height = int(trim_height * dpi)
    px_spine = int(spine_width * dpi)
    
    print(f"== KDP Cover Generator ==")
    print(f"Trim size: {trim_width}\" × {trim_height}\"")
    print(f"Page count: {page_count} pages ({paper_type} paper)")
    print(f"Spine width: {spine_width:.4f}\" ({px_spine}px)")
    print(f"Cover dimensions: {cover_width:.4f}\" × {cover_height:.4f}\"")
    print(f"Canvas size: {px_width}px × {px_height}px @ {dpi} DPI")
    print(f"Bleed: {bleed}\" ({px_bleed}px)\n")
    
    # Create base canvas (white background)
    canvas = Image.new("RGB", (px_width, px_height), "white")
    draw = ImageDraw.Draw(canvas)
    
    # Calculate regions (all from left edge)
    back_x = px_bleed
    spine_x = px_bleed + px_trim_width
    front_x = px_bleed + px_trim_width + px_spine
    
    # Position back cover (if provided)
    if back_cover_path and back_cover_path.exists():
        print(f">> Loading back cover: {back_cover_path.name}")
        back_img = Image.open(back_cover_path).convert("RGB")
        back_img = back_img.resize((px_trim_width, px_trim_height), Image.Resampling.LANCZOS)
        canvas.paste(back_img, (back_x, px_bleed))
    else:
        # Placeholder back cover
        draw.rectangle(
            [(back_x, px_bleed), (back_x + px_trim_width, px_bleed + px_trim_height)],
            fill="#E0E0E0"
        )
        draw.text(
            (back_x + px_trim_width // 2, px_bleed + px_trim_height // 2),
            "BACK COVER\nPLACEHOLDER",
            fill="black",
            anchor="mm"
        )
    
    # Position spine
    if spine_image_path and spine_image_path.exists():
        print(f">> Loading spine image: {spine_image_path.name}")
        spine_img = Image.open(spine_image_path).convert("RGB")
        spine_img = spine_img.resize((px_spine, px_trim_height), Image.Resampling.LANCZOS)
        canvas.paste(spine_img, (spine_x, px_bleed))
    elif spine_text or spine_author:
        # Generate spine from text (rotated 90° clockwise - reads bottom to top)
        text_parts = []
        if spine_text:
            text_parts.append(spine_text)
        if spine_author:
            text_parts.append(spine_author)
        
        combined_text = "  •  ".join(text_parts)  # Separator between title and author
        print(f">> Generating text spine: '{combined_text}'")
        
        # Background
        draw.rectangle(
            [(spine_x, px_bleed), (spine_x + px_spine, px_bleed + px_trim_height)],
            fill="#1a1a1a"
        )
        
        # Create temporary image for rotated text
        # PIL rotates around center, so we need height×width for the temp image
        temp_spine = Image.new("RGB", (px_trim_height, px_spine), color="#1a1a1a")
        temp_draw = ImageDraw.Draw(temp_spine)
        
        # Calculate font size that fits the spine width (narrower than before)
        # Use ~40% of spine width instead of 60% to leave more margin
        font_size = max(10, int(px_spine * 0.4))
        
        try:
            # Try to use Liberation Sans Narrow (condensed variant)
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf", font_size)
        except:
            try:
                # Fall back to DejaVu Sans Condensed
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", font_size)
            except:
                try:
                    # Fall back to regular Liberation Sans with smaller size
                    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", int(font_size * 0.8))
                except:
                    # Last resort: default font
                    font = ImageFont.load_default()
        
        # Draw text horizontally on temp image
        temp_draw.text(
            (px_trim_height // 2, px_spine // 2),
            combined_text,
            fill="white",
            font=font,
            anchor="mm"
        )
        
        # Rotate 90° clockwise (reads from bottom to top when book is spine-up)
        rotated_spine = temp_spine.rotate(-90, expand=True)
        
        # Paste rotated spine onto canvas
        canvas.paste(rotated_spine, (spine_x, px_bleed))
    else:
        # Placeholder spine
        draw.rectangle(
            [(spine_x, px_bleed), (spine_x + px_spine, px_bleed + px_trim_height)],
            fill="#999999"
        )
    
    # Position front cover (if provided)
    if front_cover_path and front_cover_path.exists():
        print(f">> Loading front cover: {front_cover_path.name}")
        front_img = Image.open(front_cover_path).convert("RGB")
        front_img = front_img.resize((px_trim_width, px_trim_height), Image.Resampling.LANCZOS)
        canvas.paste(front_img, (front_x, px_bleed))
    else:
        # Placeholder front cover
        draw.rectangle(
            [(front_x, px_bleed), (front_x + px_trim_width, px_bleed + px_trim_height)],
            fill="#F0F0F0"
        )
        draw.text(
            (front_x + px_trim_width // 2, px_bleed + px_trim_height // 2),
            "FRONT COVER\nPLACEHOLDER",
            fill="black",
            anchor="mm"
        )
    
    # Draw safety guidelines (dashed lines) - not printed, just for reference
    # These help position text/logos safely away from edges
    safety_margin = int(0.25 * dpi)  # 0.25" safety zone
    
    # Save as high-resolution PDF
    print(f"\n>> Saving cover PDF: {output_path}")
    canvas.save(output_path, "PDF", resolution=dpi, optimize=False)
    
    print(f"✓ KDP cover generated successfully\n")
    print("Next steps:")
    print("1. Review cover in a PDF viewer")
    print("2. Upload to KDP Cover Creator for validation")
    print("3. KDP will verify spine width matches page count")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate KDP-compliant print cover PDF"
    )
    parser.add_argument(
        "--profile",
        help="Build profile name (loads config from iasp-config.yaml)"
    )
    parser.add_argument(
        "--front-cover",
        type=Path,
        help="Path to front cover image (default: from config)"
    )
    parser.add_argument(
        "--back-cover",
        type=Path,
        help="Path to back cover image (default: from config)"
    )
    parser.add_argument(
        "--spine-image",
        type=Path,
        help="Path to spine graphic (optional)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/kdp-cover.pdf"),
        help="Output path for generated PDF (default: build/kdp-cover.pdf)"
    )
    parser.add_argument(
        "--page-count",
        type=int,
        help="Total page count (overrides PDF analysis)"
    )
    parser.add_argument(
        "--paper-type",
        choices=["white", "cream", "color"],
        help="Paper type for spine calculation (default: from config)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Output resolution in DPI (default: 300)"
    )
    
    args = parser.parse_args()
    
    # Load IASP config
    config = load_config()
    kdp_config = config.get("kdp", {})
    
    # Determine parameters (CLI args override config)
    front_cover = args.front_cover or (
        Path(kdp_config.get("front_cover", "cover-front.jpg"))
        if "front_cover" in kdp_config
        else None
    )
    
    back_cover = args.back_cover or (
        Path(kdp_config.get("back_cover", "cover-back.jpg"))
        if "back_cover" in kdp_config
        else None
    )
    
    spine_image = args.spine_image or (
        Path(kdp_config.get("spine_image"))
        if kdp_config.get("spine_image")
        else None
    )
    
    trim_width = kdp_config.get("trim_width", 6.0)
    trim_height = kdp_config.get("trim_height", 9.0)
    paper_type = args.paper_type or kdp_config.get("paper_type", "white")
    spine_text = kdp_config.get("spine_text")
    spine_author = kdp_config.get("spine_author")
    
    # Get page count (from arg, config, or analyze PDF)
    page_count = args.page_count
    if not page_count:
        page_count = kdp_config.get("page_count")
    if not page_count:
        # Try to get from built PDF
        pdf_path = Path("build/book.pdf")
        if pdf_path.exists():
            try:
                import PyPDF2
                with open(pdf_path, "rb") as f:
                    pdf = PyPDF2.PdfReader(f)
                    page_count = len(pdf.pages)
                print(f"Detected {page_count} pages from {pdf_path}")
            except ImportError:
                print("WARNING: PyPDF2 not available, cannot auto-detect page count")
                page_count = 300  # Default fallback
        else:
            page_count = 300  # Default fallback
    
    # Create output directory
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate cover
    create_kdp_cover(
        front_cover_path=front_cover,
        back_cover_path=back_cover,
        spine_image_path=spine_image,
        output_path=args.output,
        trim_width=trim_width,
        trim_height=trim_height,
        page_count=page_count,
        paper_type=paper_type,
        dpi=args.dpi,
        spine_text=spine_text,
        spine_author=spine_author,
    )


if __name__ == "__main__":
    main()
