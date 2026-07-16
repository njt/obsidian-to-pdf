# obsidian-to-pdf

Convert Obsidian markdown files to high-quality A4 PDFs, with full support for Obsidian's `![[wikilink]]` image syntax.

## The problem

Obsidian uses `![[filename]]` wikilinks to embed images and other files. No existing tool we found handles these wikilinks when converting to PDF — pandoc ignores them, and Obsidian's built-in PDF export offers limited control over layout and typography. If your notes embed images, diagrams, or pages from other PDFs using wikilinks, you're stuck with either broken output or manual conversion.

## What this does

A single Python script that:

- Resolves `![[image.png]]` and `![[image.png|caption]]` wikilinks by searching your vault for the referenced file
- Extracts individual pages from embedded PDFs (`![[file.pdf#page=3]]`) and renders them as high-resolution images
- Fixes pandoc list-spacing quirks so numbered and bulleted lists render correctly
- Produces a clean A4 PDF via pandoc with either **LaTeX** or **Typst** as the PDF engine
- Typst output uses the bundled **EB Garamond** font and an OUP-inspired template for classical serif typesetting

## Usage

```bash
python3 obsidian-to-pdf.py "My Note.md"
```

Output: `My Note.pdf` in the same directory.

### Engine selection

By default (`--engine auto`), the script auto-detects the best available engine:

1. **LaTeX** (xelatex, then pdflatex) — preferred when installed, best Unicode support
2. **Typst** — lightweight alternative (~30 MB vs ~4 GB for LaTeX), fast compilation

You can force a specific engine:

```bash
python3 obsidian-to-pdf.py --engine typst "My Note.md"
python3 obsidian-to-pdf.py --engine latex "My Note.md"
```

Existing users with LaTeX installed see no behaviour change — LaTeX is always preferred in auto mode.

## Requirements

**Python package:**

```bash
pip3 install pymupdf
```

**System dependencies:**

- [pandoc](https://pandoc.org/installing.html) — `brew install pandoc`
- At least one PDF engine:
  - **Typst** (easy, lightweight) — `brew install typst` — requires pandoc >= 3.1.7
  - **LaTeX** (full-featured) — `brew install --cask mactex` — provides xelatex and pdflatex

### Bundled font

The repository includes **EB Garamond** (SIL Open Font License) in `fonts/eb-garamond/`. This font is used automatically by the Typst engine for elegant serif output. No manual font installation is needed. LaTeX output is unaffected and uses whatever fonts your LaTeX distribution provides.

## Wikilink syntax supported

| Syntax | Result |
|---|---|
| `![[image.png]]` | Embedded image |
| `![[image.png\|caption]]` | Embedded image with caption |
| `![[file.pdf#page=3]]` | Page 3 of PDF rendered as image |
| `![[file.pdf#page=3\|caption]]` | PDF page with caption |

The script searches recursively from the markdown file's directory (treating it as the vault root), skipping hidden directories.

## Licence

MIT

EB Garamond font files are licensed under the [SIL Open Font License](fonts/eb-garamond/OFL.txt).
