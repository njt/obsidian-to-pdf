#!/usr/bin/env python3
"""
obsidian-to-pdf.py — Convert Obsidian markdown files to high-quality A4 PDF
using pandoc with either a LaTeX or Typst backend.

Usage:
  python3 obsidian-to-pdf.py "filename.md"
  python3 obsidian-to-pdf.py --engine typst "filename.md"
  python3 obsidian-to-pdf.py --engine latex "filename.md"
  python3 obsidian-to-pdf.py --engine auto  "filename.md"   (default)

Output: filename.pdf in the same directory as the input file.

Engine selection (--engine auto, the default):
  1. If xelatex is on PATH, use LaTeX (xelatex). Best Unicode support.
  2. Else if pdflatex is on PATH, use LaTeX (pdflatex).
  3. Else if typst is on PATH (and pandoc >= 3.1.7), use Typst.
  4. Otherwise, error with install suggestions.

Typst output uses the bundled EB Garamond font (fonts/eb-garamond/) and an
OUP-inspired template for clean, classical typesetting.

Resolves Obsidian wikilinks:
  ![[image.png]]              → embedded image
  ![[image.png|caption]]      → embedded image with caption
  ![[file.pdf#page=N]]        → extracted PDF page as image
  ![[file.pdf#page=N|caption]]→ extracted PDF page as image with caption

Requires: pip3 install pymupdf
System deps: pandoc, plus one of: xelatex/pdflatex (brew install --cask mactex)
             or typst (brew install typst)
"""

import argparse
import sys
import os
import re
import shutil
import subprocess
import tempfile

# PDF page extraction
import fitz  # pymupdf


def find_file_in_vault(filename, vault_root):
    """Recursively search for a file in the vault directory."""
    for dirpath, dirnames, filenames in os.walk(vault_root):
        # Skip hidden directories
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None


def extract_pdf_page(pdf_path, page_num, temp_dir, dpi=250):
    """Extract a page from a PDF as a PNG image, return path to the PNG."""
    try:
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > len(doc):
            print(f"  WARNING: Page {page_num} out of range for {pdf_path} (has {len(doc)} pages)")
            doc.close()
            return None
        page = doc[page_num - 1]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Save to temp directory
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        png_path = os.path.join(temp_dir, f"{base}_page{page_num}.png")
        pix.save(png_path)
        doc.close()
        return png_path
    except Exception as e:
        print(f"  WARNING: Failed to extract page {page_num} from {pdf_path}: {e}")
        return None


def resolve_wikilinks(md_text, vault_root, temp_dir):
    """Replace Obsidian ![[...]] wikilinks with standard markdown image syntax."""
    # Pattern: ![[filename#page=N|caption]] with optional #page=N and |caption
    pattern = r'!\[\[([^\]|#]+?)(?:#page=(\d+))?(?:\|([^\]]*?))?\]\]'
    resolved_count = 0

    def replace_match(m):
        nonlocal resolved_count
        filename = m.group(1).strip()
        page_num = m.group(2)
        caption = m.group(3) or ""

        if page_num:
            # PDF page extraction
            pdf_path = find_file_in_vault(filename, vault_root)
            if not pdf_path:
                print(f"  WARNING: Could not find {filename} in vault")
                return f'[Missing: {filename}#page={page_num}]'
            png_path = extract_pdf_page(pdf_path, int(page_num), temp_dir)
            if not png_path:
                return f'[Failed to extract: {filename}#page={page_num}]'
            resolved_count += 1
            return f'![{caption}]({png_path})'
        else:
            # Image embed
            image_path = find_file_in_vault(filename, vault_root)
            if not image_path:
                print(f"  WARNING: Could not find {filename} in vault")
                return f'[Missing: {filename}]'
            resolved_count += 1
            return f'![{caption}]({image_path})'

    result = re.sub(pattern, replace_match, md_text)

    # Strip regular wikilinks to plain text (not embeds — those are handled above)
    # [[page]] → page, [[page|alias]] → alias, [[page#section]] → page > section
    def strip_wikilink(m):
        target = m.group(1)
        alias = m.group(2)
        if alias:
            return alias
        # Strip #section and #^block suffixes, show as "page > section" if present
        if '#' in target:
            page, fragment = target.split('#', 1)
            fragment = fragment.lstrip('^')
            return f"{page} > {fragment}" if page else fragment
        return target

    result = re.sub(r'\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]', strip_wikilink, result)

    return result, resolved_count


def resolve_callouts(md_text):
    """Convert Obsidian callout syntax to styled markdown blockquotes.

    Transforms:
        > [!warning] Title
        > Body text

    Into:
        > **⚠️ Warning: Title**
        >
        > Body text
    """
    callout_icons = {
        'note': '📝', 'abstract': '📋', 'summary': '📋', 'tldr': '📋',
        'info': 'ℹ️', 'todo': '🔲', 'tip': '💡', 'hint': '💡',
        'important': '❗', 'success': '✅', 'check': '✅', 'done': '✅',
        'question': '❓', 'help': '❓', 'faq': '❓',
        'warning': '⚠️', 'caution': '⚠️', 'attention': '⚠️',
        'failure': '❌', 'fail': '❌', 'missing': '❌',
        'danger': '🔴', 'error': '🔴', 'bug': '🐛',
        'example': '📖', 'quote': '💬', 'cite': '💬',
    }

    lines = md_text.split('\n')
    output = []
    for line in lines:
        m = re.match(r'^>\s*\[!(\w+)\]\s*(.*)', line)
        if m:
            callout_type = m.group(1).lower()
            title = m.group(2).strip()
            icon = callout_icons.get(callout_type, '📝')
            label = callout_type.capitalize()
            if title:
                output.append(f'> **{icon} {label}: {title}**')
            else:
                output.append(f'> **{icon} {label}**')
            output.append('>')
        else:
            output.append(line)
    return '\n'.join(output)


def ensure_list_spacing(md_text):
    """Ensure blank lines before list items so pandoc recognises them as lists.

    Pandoc (especially with +hard_line_breaks) needs a blank line before the
    first list item. Without it, numbered/bulleted items render as plain text.
    """
    lines = md_text.split('\n')
    output = []
    for i, line in enumerate(lines):
        if i > 0:
            prev = lines[i - 1].strip()
            curr = line.strip()
            # If current line starts a list item and previous line is non-empty
            # and not itself a list item, insert a blank line
            is_list_start = (
                re.match(r'^\d+\.\s', curr) or
                re.match(r'^[-*+]\s', curr)
            )
            prev_is_list = (
                re.match(r'^\d+\.\s', prev) or
                re.match(r'^[-*+]\s', prev)
            )
            if is_list_start and prev and not prev_is_list:
                output.append('')
        output.append(line)
    return '\n'.join(output)


def find_tool(names):
    """Find the first available tool from a list of names."""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def detect_engine(engine_arg):
    """Detect which PDF engine to use.

    Args:
        engine_arg: One of 'auto', 'latex', 'typst'.

    Returns:
        Tuple of (engine_type, engine_name) where engine_type is 'latex' or
        'typst', and engine_name is the specific binary name (e.g. 'xelatex',
        'pdflatex', 'typst').

    Raises:
        SystemExit: If the requested engine is not available.
    """
    if engine_arg == "latex":
        path = find_tool(["xelatex", "pdflatex"])
        if not path:
            print("ERROR: No LaTeX engine found (looked for xelatex, pdflatex).")
            print("  Install with: brew install --cask mactex")
            sys.exit(1)
        return "latex", os.path.basename(path)

    if engine_arg == "typst":
        path = shutil.which("typst")
        if not path:
            print("ERROR: typst not found.")
            print("  Install with: brew install typst")
            sys.exit(1)
        return "typst", "typst"

    # auto: try LaTeX first, then Typst
    latex_path = find_tool(["xelatex", "pdflatex"])
    if latex_path:
        return "latex", os.path.basename(latex_path)

    typst_path = shutil.which("typst")
    if typst_path:
        return "typst", "typst"

    print("ERROR: No PDF engine found (looked for xelatex, pdflatex, typst).")
    print("  Easy option:         brew install typst")
    print("  Full-featured option: brew install --cask mactex")
    sys.exit(1)


def check_pandoc_version_for_typst(pandoc_path="pandoc"):
    """Verify pandoc >= 3.1.7 for Typst support.

    Args:
        pandoc_path: Path to the pandoc binary (default: "pandoc").

    Raises:
        SystemExit: If pandoc version is too old.
    """
    result = subprocess.run(
        [pandoc_path, "--version"], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("ERROR: Could not determine pandoc version.")
        print("  Install or update with: brew install pandoc")
        sys.exit(1)
    first_line = result.stdout.splitlines()[0]  # e.g. "pandoc 3.5.0"
    version_str = first_line.split()[-1]
    # Strip non-numeric suffixes like "-rc1" from version components
    parts = [int(re.match(r'(\d+)', x).group(1)) for x in version_str.split(".")]
    if tuple(parts) < (3, 1, 7):
        print(
            f"ERROR: Typst output requires pandoc >= 3.1.7 (found {version_str})."
        )
        print("  Update with: brew install pandoc")
        sys.exit(1)


LATEX_HEADER = r"""\usepackage{graphicx}
\usepackage{ragged2e}
\makeatletter
\def\maxwidth{\ifdim\Gin@nat@width>\linewidth\linewidth\else\Gin@nat@width\fi}
\makeatother
\setkeys{Gin}{width=\maxwidth,keepaspectratio}
\AtBeginDocument{\RaggedRight}
\usepackage{enumitem}
\setlist[itemize]{leftmargin=2em, itemsep=0.3em}
\setlist[enumerate]{leftmargin=2em, itemsep=0.3em}
\setlist[itemize,2]{leftmargin=1.5em}
\setlist[enumerate,2]{leftmargin=1.5em}
\setlist[itemize,3]{leftmargin=1.5em}
\setlist[enumerate,3]{leftmargin=1.5em}
\usepackage{etoolbox}
\AtBeginEnvironment{longtable}{\fontsize{10pt}{12pt}\selectfont}
"""

TYPST_TEMPLATE = r"""// OUP-inspired Typst template for obsidian-to-pdf
// Uses EB Garamond for a classical serif look

#set page(
  paper: "a4",
  margin: (left: 3.5cm, right: 3.5cm, top: 3cm, bottom: 3cm),
  header: context {
    if counter(page).get().first() > 1 [
      #set text(font: "EB Garamond", size: 9pt)
      $if(title)$#smallcaps[$title$]
      #v(-2pt)
      #line(length: 100%, stroke: 0.4pt + rgb("#999999"))$endif$
    ]
  },
  numbering: "1",
)

#set text(
  font: ("EB Garamond", "Noto Sans Symbols2"),
  size: 12pt,
  lang: "en",
)

#set par(
  justify: false,
  leading: 0.65em,
)

// Heading hierarchy — all EB Garamond SemiBold, sized proportionally
#show heading.where(level: 1): it => {
  set text(size: 20pt, weight: 600)
  v(0.5em)
  it.body
  v(0.3em)
}

#show heading.where(level: 2): it => {
  set text(size: 16pt, weight: 600)
  v(0.4em)
  it.body
  v(0.25em)
}

#show heading.where(level: 3): it => {
  set text(size: 13pt, weight: 600)
  v(0.3em)
  it.body
  v(0.2em)
}

#show heading.where(level: 4): it => {
  set text(size: 12pt, weight: 600, style: "italic")
  v(0.2em)
  it.body
  v(0.15em)
}

// Lists: 2em indent, compact spacing
#set list(indent: 2em, body-indent: 0.5em, spacing: 0.4em)
#set enum(indent: 2em, body-indent: 0.5em, spacing: 0.4em)

// Blockquotes: left bar + indentation (visually distinct from tables)
#show quote.where(block: true): it => {
  block(above: 0.8em, below: 0.8em, pad(left: 1.5em,
    block(stroke: (left: 2pt + rgb("#cccccc")), inset: (left: 1em, y: 0.4em), it.body)
  ))
}

// Code blocks: light grey background, monospace at 10pt
#show raw.where(block: true): it => {
  set text(size: 10pt)
  block(
    width: 100%,
    fill: rgb("#f5f5f5"),
    inset: 8pt,
    radius: 3pt,
    it,
  )
}

#show raw.where(block: false): set text(size: 10pt)

// Tables: 10pt, compact, minimal style (matching LaTeX booktabs look)
#show table: set text(size: 10pt)
#set table(
  stroke: none,
  inset: (x: 0.5em, y: 0.35em),
  align: left,
)
// Override pandoc's center-aligned figure wrapper and per-column auto align
#show figure.where(kind: table): set figure.caption(position: bottom)
#show figure.where(kind: table): set align(center)
#show table.cell: set align(left)
#show table.cell.where(y: 0): it => {
  set text(weight: "regular")
  it
}
// Booktabs-style table rules: heavy top/bottom, thin after header
// Pandoc emits table.hline() after the header row — set its default to thin
#set table.hline(stroke: 0.5pt)
// Use cell stroke to draw heavy top on first row and heavy bottom on all rows
// (only the last row's bottom will be visible)
#set table(
  stroke: (x, y) => (
    left: 0pt, right: 0pt,
    top: if y == 0 { 1.2pt } else { 0pt },
    bottom: 1.2pt,
  ),
)

// Images: use natural size (Typst already constrains to container width)

// Horizontal rule (pandoc emits #horizontalrule for ---)
#let horizontalrule = line(length: 100%, stroke: 0.5pt + rgb("#cccccc"))

// Title block with date (matching pandoc's LaTeX \maketitle)
$if(title)$
#align(center)[
  #text(size: 20pt, weight: 600)[$title$]
  $if(date)$
  #v(0.3em)
  #text(size: 11pt, fill: rgb("#555555"))[$date$]
  $endif$
  $if(author)$
  #v(0.2em)
  #text(size: 11pt, fill: rgb("#555555"))[$author$]
  $endif$
]
#v(1em)
$endif$

$body$
"""


def mermaid_filter_args():
    """Return pandoc filter args for Mermaid diagrams if available."""
    if shutil.which("mermaid-filter"):
        return ["--filter", "mermaid-filter"]
    if shutil.which("mmdc"):
        # mmdc is the Mermaid CLI; mermaid-filter wraps it for pandoc
        # Without mermaid-filter, we can't use it directly
        pass
    return []


def build_latex_cmd(pandoc, engine_name, output_path, header_path, md_path):
    """Build the pandoc command for LaTeX output."""
    cmd = [
        pandoc,
        "-f", "markdown+hard_line_breaks",
        "-o", output_path,
        f"--pdf-engine={engine_name}",
        "-V", "geometry:a4paper",
        "-V", "geometry:left=3.5cm,right=3.5cm,top=3cm,bottom=3cm",
        "-V", "fontsize=12pt",
        "--standalone",
        f"--include-in-header={header_path}",
    ]
    cmd.extend(mermaid_filter_args())
    cmd.append(md_path)
    return cmd


def build_typst_cmd(pandoc, output_path, template_path, font_dir, md_path):
    """Build the pandoc command for Typst output."""
    cmd = [
        pandoc,
        "-f", "markdown+hard_line_breaks",
        "-t", "typst",
        f"--template={template_path}",
        "--pdf-engine-opt=--font-path",
        f"--pdf-engine-opt={font_dir}",
        "-o", output_path,
    ]
    cmd.extend(mermaid_filter_args())
    cmd.append(md_path)
    return cmd


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert Obsidian markdown files to high-quality A4 PDF.",
    )
    parser.add_argument(
        "input_file",
        help="Path to the Obsidian markdown file to convert.",
    )
    parser.add_argument(
        "--engine",
        choices=["typst", "latex", "auto"],
        default="auto",
        help="PDF engine to use (default: auto — tries LaTeX first, then Typst).",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    input_path = args.input_file

    # Resolve to absolute path
    if not os.path.isabs(input_path):
        input_path = os.path.join(os.getcwd(), input_path)

    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    # Check pandoc
    pandoc = find_tool(["pandoc"])
    if not pandoc:
        print("ERROR: pandoc not found. Install with: brew install pandoc")
        sys.exit(1)

    # Detect engine
    engine, engine_name = detect_engine(args.engine)

    # If Typst, check pandoc version
    if engine == "typst":
        check_pandoc_version_for_typst(pandoc)

    reason = "auto-detected" if args.engine == "auto" else "explicitly selected"
    print(f"Using PDF engine: {engine_name} ({reason})")

    # Vault root = directory containing the md file
    vault_root = os.path.dirname(os.path.abspath(input_path))
    output_path = os.path.splitext(input_path)[0] + '.pdf'
    basename = os.path.basename(input_path)

    print(f"Converting: {basename}")
    print(f"Vault root: {vault_root}")

    # Read markdown
    with open(input_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Create temp directory for extracted PDF pages, header/template files
    temp_dir = tempfile.mkdtemp(prefix="obsidian-pdf-")
    try:
        # Resolve wikilinks
        print("Resolving wikilinks...")
        md_text, resolved_count = resolve_wikilinks(md_text, vault_root, temp_dir)
        print(f"  Resolved {resolved_count} image(s)")

        # Convert Obsidian callouts to styled blockquotes
        md_text = resolve_callouts(md_text)

        # Ensure blank lines before lists for proper pandoc parsing
        md_text = ensure_list_spacing(md_text)

        # Write processed markdown to a temp file
        md_path = os.path.join(temp_dir, "input.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_text)

        # Build engine-specific command
        if engine == "typst":
            # Write Typst template to temp file
            template_path = os.path.join(temp_dir, "template.typst")
            with open(template_path, 'w') as f:
                f.write(TYPST_TEMPLATE)

            font_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "fonts",
            )
            cmd = build_typst_cmd(pandoc, output_path, template_path, font_dir, md_path)
        else:
            # Write LaTeX header-includes to a temp file
            header_path = os.path.join(temp_dir, "header.tex")
            with open(header_path, 'w') as f:
                f.write(LATEX_HEADER)
            cmd = build_latex_cmd(pandoc, engine_name, output_path, header_path, md_path)

        print(f"Running pandoc...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=vault_root,
        )

        if result.returncode != 0:
            print(f"ERROR: pandoc failed (exit code {result.returncode})")
            if result.stderr:
                print(result.stderr)
            sys.exit(1)

        if result.stderr:
            # pandoc warnings (non-fatal)
            print(f"  Warnings: {result.stderr.strip()}")

        file_size = os.path.getsize(output_path)
        print(f"SUCCESS: {output_path}")
        print(f"  Size: {file_size / 1024 / 1024:.1f} MB ({file_size / 1024:.0f} KB)")

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
