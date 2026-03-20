#!/usr/bin/env python3
"""Visual comparison harness for LaTeX vs Typst output.

For each .md file in test-vault/, renders with both engines, then composites
side-by-side into landscape sheets in a single comparison.pdf.

Usage:
    python3 compare_engines.py                    # all test vault files
    python3 compare_engines.py "Trycycle Overview" # one file (partial match)

Requires: pandoc, xelatex (or pdflatex), typst, pymupdf
"""

import glob
import os
import subprocess
import sys
import tempfile

import fitz  # PyMuPDF

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONVERTER = os.path.join(SCRIPT_DIR, "obsidian-to-pdf.py")
TEST_VAULT = os.path.join(SCRIPT_DIR, "test-vault")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "comparison.pdf")

# Landscape A3 dimensions in points (A3 = 297mm x 420mm)
A3_W = 420 * 72 / 25.4  # ~1190.55 pt
A3_H = 297 * 72 / 25.4  # ~841.89 pt

BANNER_H = 28
LABEL_H = 16
MARGIN = 8


def render_pdf(md_path, engine, output_dir):
    """Run obsidian-to-pdf.py for a given engine, return output PDF path or None."""
    basename = os.path.splitext(os.path.basename(md_path))[0]
    out_path = os.path.join(output_dir, f"{basename}_{engine}.pdf")

    # We need to copy the md to output_dir so the PDF lands there
    # Actually, the script puts PDF next to the input. We'll use a symlink trick:
    # just run it and then move the output.
    result = subprocess.run(
        [sys.executable, CONVERTER, "--engine", engine, md_path],
        capture_output=True, text=True,
        env={**os.environ, "PATH": f"/Library/TeX/texbin:{os.environ.get('PATH', '')}"},
    )

    # The PDF lands next to the input file
    default_out = os.path.splitext(md_path)[0] + ".pdf"

    if result.returncode != 0:
        print(f"  FAILED ({engine}): {result.stderr.strip()[:200]}")
        return None

    if not os.path.exists(default_out):
        print(f"  FAILED ({engine}): no output PDF produced")
        return None

    # Move to our output dir with engine suffix
    os.rename(default_out, out_path)
    return out_path


def compose_comparison(latex_pdf_path, typst_pdf_path, source_name, output_doc):
    """Add side-by-side comparison sheets to the output document."""
    latex_doc = fitz.open(latex_pdf_path) if latex_pdf_path else None
    typst_doc = fitz.open(typst_pdf_path) if typst_pdf_path else None

    latex_pages = len(latex_doc) if latex_doc else 0
    typst_pages = len(typst_doc) if typst_doc else 0
    max_pages = max(latex_pages, typst_pages)

    if max_pages == 0:
        print(f"  SKIP: no pages for {source_name}")
        return

    for page_num in range(max_pages):
        # Create landscape A3 page
        page = output_doc.new_page(width=A3_W, height=A3_H)

        mid_x = A3_W / 2
        content_top = BANNER_H + LABEL_H
        content_w = mid_x - MARGIN * 2
        content_h = A3_H - content_top - MARGIN

        # --- Banner ---
        banner_rect = fitz.Rect(0, 0, A3_W, BANNER_H)
        page.draw_rect(banner_rect, color=None, fill=(0.17, 0.24, 0.31))  # #2c3e50
        page.insert_text(
            (12, BANNER_H - 8),
            f"{source_name}",
            fontsize=12, fontname="helv", color=(1, 1, 1),
        )
        page_label = f"Page {page_num + 1} of {max_pages}"
        # Right-align page label
        tw = fitz.get_text_length(page_label, fontsize=10, fontname="helv")
        page.insert_text(
            (A3_W - tw - 12, BANNER_H - 9),
            page_label,
            fontsize=10, fontname="helv", color=(0.7, 0.7, 0.7),
        )

        # --- Divider line ---
        page.draw_line((mid_x, BANNER_H), (mid_x, A3_H), color=(0.8, 0.8, 0.8), width=0.5)

        # --- Left label: LaTeX ---
        page.insert_text(
            (MARGIN + 4, BANNER_H + LABEL_H - 4),
            "LATEX",
            fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4),
        )

        # --- Right label: Typst (EB Garamond) ---
        page.insert_text(
            (mid_x + MARGIN + 4, BANNER_H + LABEL_H - 4),
            "TYPST (EB GARAMOND)",
            fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4),
        )

        # --- Left half: LaTeX page ---
        left_rect = fitz.Rect(MARGIN, content_top, mid_x - MARGIN, content_top + content_h)
        if latex_doc and page_num < latex_pages:
            page.show_pdf_page(left_rect, latex_doc, page_num)
        else:
            # No page — draw placeholder
            page.draw_rect(left_rect, color=(0.9, 0.9, 0.9), fill=(0.97, 0.97, 0.97))
            cx = left_rect.x0 + left_rect.width / 2
            cy = left_rect.y0 + left_rect.height / 2
            text = "No page" if latex_pdf_path else "LaTeX render failed"
            tw = fitz.get_text_length(text, fontsize=11, fontname="helv")
            page.insert_text((cx - tw / 2, cy), text, fontsize=11, fontname="helv", color=(0.6, 0.6, 0.6))

        # --- Right half: Typst page ---
        right_rect = fitz.Rect(mid_x + MARGIN, content_top, A3_W - MARGIN, content_top + content_h)
        if typst_doc and page_num < typst_pages:
            page.show_pdf_page(right_rect, typst_doc, page_num)
        else:
            page.draw_rect(right_rect, color=(0.9, 0.9, 0.9), fill=(0.97, 0.97, 0.97))
            cx = right_rect.x0 + right_rect.width / 2
            cy = right_rect.y0 + right_rect.height / 2
            text = "No page" if typst_pdf_path else "Typst render failed"
            tw = fitz.get_text_length(text, fontsize=11, fontname="helv")
            page.insert_text((cx - tw / 2, cy), text, fontsize=11, fontname="helv", color=(0.6, 0.6, 0.6))

    if latex_doc:
        latex_doc.close()
    if typst_doc:
        typst_doc.close()


def main():
    # Find test vault files
    md_files = sorted(glob.glob(os.path.join(TEST_VAULT, "*.md")))

    if not md_files:
        print(f"No .md files found in {TEST_VAULT}")
        sys.exit(1)

    # Filter if argument given
    if len(sys.argv) > 1:
        query = sys.argv[1].lower()
        md_files = [f for f in md_files if query in os.path.basename(f).lower()]
        if not md_files:
            print(f"No files matching '{sys.argv[1]}' in {TEST_VAULT}")
            sys.exit(1)

    print(f"Comparing {len(md_files)} file(s)...")
    print()

    output_doc = fitz.open()

    with tempfile.TemporaryDirectory(prefix="compare-engines-") as tmp_dir:
        for md_path in md_files:
            name = os.path.splitext(os.path.basename(md_path))[0]
            print(f"--- {name} ---")

            print(f"  Rendering LaTeX...")
            latex_pdf = render_pdf(md_path, "latex", tmp_dir)

            print(f"  Rendering Typst...")
            typst_pdf = render_pdf(md_path, "typst", tmp_dir)

            if not latex_pdf and not typst_pdf:
                print(f"  SKIP: both engines failed")
                continue

            compose_comparison(latex_pdf, typst_pdf, name, output_doc)
            print(f"  OK")

    page_count = len(output_doc)
    if page_count == 0:
        print("\nNo pages to compare — both engines failed for all files.")
        sys.exit(1)

    output_doc.save(OUTPUT_FILE)
    output_doc.close()
    print(f"\nComparison saved: {OUTPUT_FILE} ({page_count} pages)")
    print(f"Open with: open {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
