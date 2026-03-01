#!/usr/bin/env python3
"""
optimize_pdf.py

Standalone script to optimize PDF files for better compatibility with
Google Drive and online PDF viewers.

Uses qpdf to linearize PDFs for Adobe Document Cloud while preserving
all PDF metadata (title, author, keywords, etc.).

Usage:
    python3 optimize_pdf.py <input.pdf>
    python3 optimize_pdf.py <input.pdf> <output.pdf>
    python3 optimize_pdf.py build/articles/*.pdf

Examples:
    # Optimize in-place (replaces original)
    python3 optimize_pdf.py build/articles/example.pdf

    # Save to a different file
    python3 optimize_pdf.py input.pdf output-optimized.pdf

    # Batch optimize all article PDFs
    python3 optimize_pdf.py build/articles/*.pdf
"""

import shutil
import subprocess
import sys
from pathlib import Path


def check_qpdf() -> bool:
    """Check if qpdf is available."""
    try:
        subprocess.run(
            ["qpdf", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def optimize_pdf(input_path: Path, output_path: Path | None = None) -> bool:
    """
    Optimize a PDF file using qpdf.
    
    Args:
        input_path: Path to input PDF
        output_path: Path to output PDF (or None to replace input)
    
    Returns:
        True if successful, False otherwise
    """
    if not input_path.exists():
        print(f"!! Input file not found: {input_path}")
        return False
    
    if not input_path.suffix.lower() == ".pdf":
        print(f"!! Not a PDF file: {input_path}")
        return False
    
    # Use temporary file if replacing in-place
    if output_path is None:
        temp_path = input_path.with_suffix(".optimized.pdf")
        replace_original = True
    else:
        temp_path = output_path
        replace_original = False
    
    print(f"Optimizing: {input_path.name}")
    
    qpdf_cmd = [
        "qpdf",
        "--linearize",  # Create linearized (web-optimized) PDF
        "--compress-streams=y",
        "--object-streams=generate",
        str(input_path),
        str(temp_path),
    ]
        str(temp_path),
    ]
    
    result = subprocess.run(qpdf_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"!! Optimization failed with exit code {result.returncode}")
        if result.stderr:
            print(result.stderr)
        if temp_path.exists():
            temp_path.unlink()
        return False
    
    if replace_original:
        try:
            shutil.move(str(temp_path), str(input_path))
            print(f"   ✓ Optimized (replaced original)")
        except OSError as exc:
            print(f"!! Failed to replace original: {exc}")
            if temp_path.exists():
                temp_path.unlink()
            return False
    else:
        print(f"   ✓ Saved to: {output_path}")
    
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 optimize_pdf.py <input.pdf> [output.pdf]")
        print("       python3 optimize_pdf.py build/articles/*.pdf")
        sys.exit(1)
    
    if not check_qpdf():
        print("!! qpdf not found or not working.")
        print("   Install with: sudo apt install qpdf")
        sys.exit(1)
    
    inputs = [Path(arg) for arg in sys.argv[1:]]
    
    # Check if last argument is an output path (single file mode)
    if len(inputs) == 2 and not inputs[1].exists():
        # Two arguments: input and output
        input_pdf = inputs[0]
        output_pdf = inputs[1]
        success = optimize_pdf(input_pdf, output_pdf)
        sys.exit(0 if success else 1)
    
    # Batch mode: optimize all inputs in-place
    total = len(inputs)
    succeeded = 0
    failed = 0
    
    print(f"\nOptimizing {total} PDF file(s)...\n")
    
    for input_pdf in inputs:
        if optimize_pdf(input_pdf):
            succeeded += 1
        else:
            failed += 1
    
    print(f"\n== Complete: {succeeded} optimized, {failed} failed ==")
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
