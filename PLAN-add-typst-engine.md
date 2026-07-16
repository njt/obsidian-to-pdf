# Plan: Add Typst as an alternative PDF engine

## Motivation

The current pipeline is pandoc + LaTeX (xelatex/pdflatex). LaTeX is a ~4 GB install
(`mactex`) and compilation is slow. Typst is a modern typesetting system that is a single
~30 MB binary, compiles in milliseconds, and pandoc gained Typst output support in v3.1.7
(`-t typst`). Adding Typst as an engine option makes the tool dramatically easier to set up
and faster to run, while keeping LaTeX as the primary engine for users who already have it.

## Design decisions

1. **Auto-detect with manual override.** A `--engine typst|latex|auto` flag (default `auto`)
   lets users force an engine. Auto-detection checks for LaTeX first (`xelatex`, then
   `pdflatex`), then Typst — matching the user's stated preference for LaTeX-first ordering.
   This means existing users with LaTeX installed see no behaviour change.
2. **Bundle EB Garamond.** The EB Garamond font (OFL-licensed) ships in `fonts/eb-garamond/`
   so Typst output looks elegant without requiring the user to install fonts. The font files
   are pointed to via Typst's `--font-path` flag. LaTeX output is unaffected (it continues
   using whatever fonts the LaTeX distribution provides).
3. **OUP-inspired Typst template.** The Typst template produces output inspired by Oxford
   University Press house style: EB Garamond serif body text, tasteful heading hierarchy,
   running headers, generous margins, and refined spacing. This lives as a `TYPST_TEMPLATE`
   constant in the script, written to a temp file at runtime.
4. **Shared pre-processing.** Wikilink resolution and list-spacing fixup are engine-agnostic
   and stay exactly as they are.

## Implementation steps

### Step 1 — Bundle EB Garamond font

Create `fonts/eb-garamond/` containing the EB Garamond OTF files and the OFL license:

```
fonts/eb-garamond/
  EBGaramond-Regular.otf
  EBGaramond-Italic.otf
  EBGaramond-Bold.otf
  EBGaramond-BoldItalic.otf
  EBGaramond-SemiBold.otf
  EBGaramond-SemiBoldItalic.otf
  OFL.txt
```

Download from the official Google Fonts repository
(https://github.com/googlefonts/eb-garamond). Include only OTF statics — no variable fonts,
no TTFs, no web fonts. Add `OFL.txt` (the SIL Open Font License) alongside the font files.

### Step 2 — CLI argument parsing

Replace the bare `sys.argv` access with `argparse`.

- Positional arg: input markdown file (required).
- `--engine {typst,latex,auto}` — default `auto`.
- Auto-detection logic when `--engine auto`:
  1. Check for `xelatex` on PATH, then `pdflatex`. If found, use LaTeX.
  2. Otherwise check for `typst` on PATH. If found, use Typst.
  3. If neither is found, error with a message suggesting `brew install typst` (easy) or
     `brew install --cask mactex` (full-featured).

When `--engine latex` or `--engine typst` is explicit, check only for the requested engine
and error if not found.

### Step 3 — OUP-inspired Typst template

Create a `TYPST_TEMPLATE` constant string. This is a pandoc template (using `$body$` and
other pandoc template variables) that produces OUP-inspired output:

- **Page:** A4, margins 3.5cm left/right, 3cm top/bottom (matching the LaTeX config).
- **Body text:** EB Garamond at 12pt, ragged right (matching LaTeX's `\RaggedRight`).
- **Headings:** EB Garamond SemiBold, sized proportionally (e.g., H1 at 20pt, H2 at 16pt,
  H3 at 13pt). No colour, no sans-serif — pure classical serif hierarchy.
- **Running header:** Document title (from `$title$`) in small caps at the top of each page
  after the first, with a thin rule beneath.
- **Lists:** 2em left indent, 0.3em item spacing (matching LaTeX enumitem settings).
- **Tables:** 10pt font size for table content (matching the LaTeX `\AtBeginEnvironment`).
- **Code blocks:** A light grey background, monospace font at 10pt.
- **Math:** Typst's built-in math rendering (no extra config needed).
- **Footnotes:** Standard Typst footnote rendering.

The template is written to a temp file at runtime and passed via `--template`.

### Step 4 — Refactor `main()` into engine-specific command builders

Extract two functions:

- `build_latex_cmd(pandoc, engine_name, output_path, header_path, md_path)` — returns the
  existing pandoc command list, unchanged from current behaviour.
- `build_typst_cmd(pandoc, output_path, template_path, font_dir, md_path)` — returns:
  ```
  pandoc -f markdown+hard_line_breaks -t typst
         --template=<template_path>
         --pdf-engine-opt=--font-path
         --pdf-engine-opt=<font_dir>
         -o <output_path> <md_path>
  ```
  Pandoc handles Typst compilation internally when the output is `.pdf` and `-t typst` is
  set (pandoc invokes `typst compile` under the hood), so no separate `typst` invocation is
  needed. The `--pdf-engine-opt=--font-path` passes the bundled font directory to Typst so
  it can find EB Garamond without system-wide installation.

### Step 5 — Wire it together in `main()`

After wikilink resolution and list-spacing fixup:

```python
font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "eb-garamond")

if engine == "typst":
    write typst template to temp file
    cmd = build_typst_cmd(pandoc, output_path, template_path, font_dir, md_path)
else:
    write latex header to temp file
    cmd = build_latex_cmd(pandoc, engine_name, output_path, header_path, md_path)
subprocess.run(cmd, ...)
```

Print which engine was selected and why (auto-detected vs forced).

### Step 6 — Pandoc version check

When the Typst engine is selected, check `pandoc --version` and verify the version is
>= 3.1.7. If too old, print a clear error:
`ERROR: Typst output requires pandoc >= 3.1.7 (found X.Y.Z). Update with: brew install pandoc`

### Step 7 — Update docstring and README

- Update the module docstring at the top of `obsidian-to-pdf.py` to mention Typst support
  and the `--engine` flag.
- Update `README.md`:
  - Add Typst to the Requirements section (`brew install typst`).
  - Document the `--engine` flag.
  - Note that LaTeX is preferred when both are available; Typst is the lightweight fallback.
  - Mention the bundled EB Garamond font.

### Step 8 — Development smoke tests

Create `test_engines.py` with automated smoke tests for our development use (not for
upstream). These use `subprocess` to invoke the script and verify basic correctness:

- **Test: LaTeX produces PDF.** Run `obsidian-to-pdf.py --engine latex` against a test vault
  file. Assert exit code 0 and output file exists with size > 1 KB. Skip if `xelatex` not
  on PATH.
- **Test: Typst produces PDF.** Same, with `--engine typst`. Skip if `typst` not on PATH.
- **Test: auto-detect selects an engine.** Run with `--engine auto` and assert exit code 0
  (skip if neither engine is available).
- **Test: explicit engine not found.** Run `--engine typst` with PATH manipulated to hide
  `typst`. Assert non-zero exit code and "not found" in stderr/stdout.
- **Test: all test vault files.** Loop over `test-vault/*.md`, run with each available
  engine, assert exit code 0 and PDF output for each.

Use `pytest` with `skipIf` decorators for engine availability. These tests are for our
development confidence, not packaged for upstream.

## Files changed

| File | Change |
|---|---|
| `obsidian-to-pdf.py` | argparse, engine detection, Typst template, command builders, font path |
| `README.md` | Document Typst option, `--engine` flag, EB Garamond |
| `fonts/eb-garamond/*.otf` | Bundled EB Garamond font files (6 OTF files) |
| `fonts/eb-garamond/OFL.txt` | SIL Open Font License for EB Garamond |
| `test_engines.py` | Development smoke tests |

## Risks and mitigations

- **Pandoc version requirement.** Typst output requires pandoc >= 3.1.7. Step 6 adds an
  explicit version check with a clear error message.
- **Font bundling size.** The 6 EB Garamond OTF files are ~1.5 MB total. This is acceptable
  for the quality improvement and eliminates a user dependency.
- **Visual parity.** LaTeX and Typst output will not be pixel-identical. This is acceptable;
  both should be clean and readable. The LaTeX path is unchanged so existing users see no
  difference.
- **Typst template completeness.** Pandoc's Typst writer may produce constructs that need
  template-level handling (e.g., callout blocks become blockquotes). The template should be
  tested against all test vault files to catch rendering issues.
- **`--pdf-engine-opt` font path.** This pandoc flag passes options through to the underlying
  typst invocation. If pandoc changes how it invokes typst, this could break. This is the
  documented pandoc interface, so breakage is unlikely.
