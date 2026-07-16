# Test plan: Add Typst as an alternative PDF engine

Date: 2026-03-21
Implementation plan: `PLAN-add-typst-engine.md`

---

## 1. End-to-end CLI tests (~60% effort)

### Test 1: LaTeX engine produces valid PDF from simple markdown

- **Name**: LaTeX engine produces a valid, non-trivial PDF from a test vault file
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + subprocess
- **Preconditions**: `xelatex` or `pdflatex` on PATH; `pandoc` on PATH; test vault exists at `test-vault/`
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine latex "test-vault/Trycycle Overview.md"`
  2. Capture exit code, stdout, stderr
- **Expected outcome**:
  - Exit code 0
  - `test-vault/Trycycle Overview.pdf` exists
  - PDF file size > 1 KB
  - stdout contains "Using PDF engine:" and one of "xelatex" or "pdflatex"
- **Interactions**: pandoc, xelatex/pdflatex, filesystem
- **Skip condition**: `pytest.mark.skipif` if neither `xelatex` nor `pdflatex` on PATH

### Test 2: Typst engine produces valid PDF from simple markdown

- **Name**: Typst engine produces a valid, non-trivial PDF from a test vault file
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + subprocess
- **Preconditions**: `typst` on PATH; `pandoc` >= 3.1.7 on PATH; test vault exists; bundled EB Garamond fonts present in `fonts/eb-garamond/`
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine typst "test-vault/Trycycle Overview.md"`
  2. Capture exit code, stdout, stderr
- **Expected outcome**:
  - Exit code 0
  - `test-vault/Trycycle Overview.pdf` exists
  - PDF file size > 1 KB
  - stdout contains "Using PDF engine:" and "typst"
- **Interactions**: pandoc, typst, filesystem, bundled fonts
- **Skip condition**: `pytest.mark.skipif` if `typst` not on PATH or pandoc < 3.1.7

### Test 3: Typst PDF contains expected text content

- **Name**: Typst-generated PDF contains the document title and body text
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF (fitz) for text extraction
- **Preconditions**: Same as Test 2; `pymupdf` installed
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine typst "test-vault/Trycycle Overview.md"`
  2. Open the resulting PDF with `fitz.open()`
  3. Extract text from all pages
- **Expected outcome**:
  - Extracted text contains "Trycycle" (the title)
  - Extracted text contains "hill climber" (body content)
  - Extracted text contains "Planning" (list item content)
- **Interactions**: pandoc, typst, PyMuPDF
- **Skip condition**: Same as Test 2

### Test 4: LaTeX PDF contains expected text content

- **Name**: LaTeX-generated PDF contains the document title and body text
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF (fitz) for text extraction
- **Preconditions**: Same as Test 1; `pymupdf` installed
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine latex "test-vault/Trycycle Overview.md"`
  2. Open the resulting PDF with `fitz.open()`
  3. Extract text from all pages
- **Expected outcome**:
  - Extracted text contains "Trycycle"
  - Extracted text contains "hill climber"
  - Extracted text contains "Planning"
- **Interactions**: pandoc, xelatex/pdflatex, PyMuPDF
- **Skip condition**: Same as Test 1

### Test 5: Typst PDF embeds EB Garamond font

- **Name**: Typst output uses the bundled EB Garamond font
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF font inspection
- **Preconditions**: Same as Test 2
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine typst "test-vault/Trycycle Overview.md"`
  2. Open PDF with `fitz.open()`
  3. Iterate pages, collect font names via `page.get_fonts()`
- **Expected outcome**:
  - At least one font name contains "Garamond" (case-insensitive)
- **Interactions**: pandoc, typst, PyMuPDF, bundled fonts
- **Skip condition**: Same as Test 2

### Test 6: All test vault files produce PDFs with each engine

- **Name**: Every markdown file in test-vault converts successfully with each available engine
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest parametrize over (engine, md_file) combinations
- **Preconditions**: Test vault files exist; at least one engine available
- **Actions**:
  1. For each `.md` file in `test-vault/` and each available engine (`latex`, `typst`):
     - Run `python3 obsidian-to-pdf.py --engine <engine> "<file>"`
     - Capture exit code
- **Expected outcome**:
  - Exit code 0 for every combination
  - Corresponding `.pdf` file exists and size > 1 KB
- **Interactions**: pandoc, xelatex/pdflatex/typst, filesystem
- **Skip condition**: Skip engine if not available on PATH

### Test 7: Wikilink image embedding works in Typst output

- **Name**: An Obsidian wikilink image embed resolves and appears in Typst PDF
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF
- **Preconditions**: Same as Test 2; `test-vault/Superpowers.md` contains `![[superpowers-banner.png]]`; image exists at `test-vault/attachments/superpowers-banner.png`
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine typst "test-vault/Superpowers.md"`
  2. Open resulting PDF, check for images on page 1 via `page.get_images()`
- **Expected outcome**:
  - Exit code 0
  - PDF page 1 contains at least one embedded image
  - stdout mentions "Resolved 1 image(s)"
- **Interactions**: pandoc, typst, wikilink resolver, filesystem
- **Skip condition**: Same as Test 2

---

## 2. Engine selection and CLI flag tests (~20% effort)

### Test 8: --engine auto selects LaTeX when both engines available

- **Name**: Auto-detection prefers LaTeX over Typst when both are installed
- **Type**: unit
- **Disposition**: new
- **Harness**: pytest + unittest.mock (patch `shutil.which`)
- **Preconditions**: Script importable or engine detection logic extracted to testable function
- **Actions**:
  1. Patch `shutil.which` to return `/usr/local/bin/xelatex` for `xelatex`, `/usr/local/bin/typst` for `typst`, and a valid path for `pandoc`
  2. Call engine detection function with `engine="auto"`
- **Expected outcome**:
  - Returns `"latex"` (not `"typst"`)
  - The selected LaTeX variant is `"xelatex"`
- **Interactions**: `shutil.which` mock

### Test 9: --engine auto selects Typst when only Typst available

- **Name**: Auto-detection falls back to Typst when no LaTeX engine is found
- **Type**: unit
- **Disposition**: new
- **Harness**: pytest + unittest.mock
- **Preconditions**: Same as Test 8
- **Actions**:
  1. Patch `shutil.which` to return `None` for `xelatex` and `pdflatex`, valid path for `typst` and `pandoc`
  2. Call engine detection with `engine="auto"`
- **Expected outcome**:
  - Returns `"typst"`
- **Interactions**: `shutil.which` mock

### Test 10: --engine auto prefers xelatex over pdflatex

- **Name**: Auto-detection prefers xelatex over pdflatex for Unicode support
- **Type**: unit
- **Disposition**: new
- **Harness**: pytest + unittest.mock
- **Preconditions**: Same as Test 8
- **Actions**:
  1. Patch `shutil.which` to return valid paths for both `xelatex` and `pdflatex`
  2. Call engine detection with `engine="auto"`
- **Expected outcome**:
  - Selected engine name is `"xelatex"` (not `"pdflatex"`)
- **Interactions**: `shutil.which` mock

### Test 11: --engine auto errors when no engine available

- **Name**: Script exits with helpful error when no PDF engine is found
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + subprocess with restricted PATH
- **Preconditions**: Script on filesystem
- **Actions**:
  1. Run script with `PATH` set to empty/minimal (only python, pandoc — no xelatex, pdflatex, typst)
  2. Or: patch `shutil.which` to return None for all engines and call detection function
- **Expected outcome**:
  - Non-zero exit code (or `SystemExit`)
  - Output contains "not found" or error text
  - Output suggests `brew install typst` and `brew install --cask mactex`
- **Interactions**: `shutil.which` mock or PATH manipulation

### Test 12: --engine typst errors when Typst not installed

- **Name**: Explicit --engine typst fails clearly when typst binary is missing
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + subprocess with restricted PATH (or mock)
- **Preconditions**: Script on filesystem
- **Actions**:
  1. Run script with `--engine typst` and PATH that excludes `typst`
- **Expected outcome**:
  - Non-zero exit code
  - Output contains "not found" or similar error about typst
- **Interactions**: `shutil.which` / PATH

### Test 13: --engine latex errors when LaTeX not installed

- **Name**: Explicit --engine latex fails clearly when no LaTeX engine is found
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + subprocess with restricted PATH (or mock)
- **Preconditions**: Script on filesystem
- **Actions**:
  1. Run script with `--engine latex` and PATH that excludes `xelatex` and `pdflatex`
- **Expected outcome**:
  - Non-zero exit code
  - Output contains "not found" or similar error about LaTeX
- **Interactions**: `shutil.which` / PATH

### Test 14: Pandoc version check rejects old pandoc for Typst

- **Name**: Script refuses Typst engine when pandoc version is < 3.1.7
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + unittest.mock (patch `subprocess.run` for `pandoc --version`)
- **Preconditions**: Engine detection selects Typst
- **Actions**:
  1. Mock `pandoc --version` to return `"pandoc 3.1.6"`
  2. Attempt to run with `--engine typst`
- **Expected outcome**:
  - Non-zero exit code or error raised
  - Output contains "pandoc >= 3.1.7" and the found version
- **Interactions**: subprocess mock

### Test 15: Pandoc version check accepts sufficient pandoc for Typst

- **Name**: Script accepts pandoc >= 3.1.7 for Typst engine
- **Type**: unit
- **Disposition**: new
- **Harness**: pytest + unittest.mock
- **Preconditions**: Same as Test 14
- **Actions**:
  1. Mock `pandoc --version` to return `"pandoc 3.1.7"` then `"pandoc 3.5.0"`
  2. Attempt Typst engine selection
- **Expected outcome**:
  - No version error raised for either version
- **Interactions**: subprocess mock

### Test 16: Invalid --engine value rejected by argparse

- **Name**: Script rejects unrecognized engine names
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + subprocess
- **Preconditions**: Script on filesystem
- **Actions**:
  1. Run `python3 obsidian-to-pdf.py --engine foobar "test-vault/Trycycle Overview.md"`
- **Expected outcome**:
  - Non-zero exit code
  - stderr contains "invalid choice" or similar argparse error
- **Interactions**: argparse

---

## 3. Regression tests for existing functions (~10% effort)

### Test 17: resolve_wikilinks handles image embeds

- **Name**: Wikilink resolver converts `![[image.png]]` to standard markdown image syntax
- **Type**: regression
- **Disposition**: new
- **Harness**: pytest (direct function call)
- **Preconditions**: A temporary directory with a test image file
- **Actions**:
  1. Create a temp directory with a file `photo.png`
  2. Call `resolve_wikilinks("Look: ![[photo.png]]", vault_root=temp_dir, temp_dir=temp_dir)`
- **Expected outcome**:
  - Result text matches `"Look: ![](/<path>/photo.png)"`
  - Resolved count is 1
- **Interactions**: filesystem (os.walk)

### Test 18: resolve_wikilinks handles caption syntax

- **Name**: Wikilink resolver preserves caption text from `![[image.png|My Caption]]`
- **Type**: regression
- **Disposition**: new
- **Harness**: pytest (direct function call)
- **Preconditions**: Same as Test 17
- **Actions**:
  1. Call `resolve_wikilinks("![[photo.png|A nice photo]]", vault_root=temp_dir, temp_dir=temp_dir)`
- **Expected outcome**:
  - Result text contains `![A nice photo](`
  - Resolved count is 1
- **Interactions**: filesystem

### Test 19: resolve_wikilinks reports missing files gracefully

- **Name**: Wikilink resolver returns placeholder text for missing files without crashing
- **Type**: regression
- **Disposition**: new
- **Harness**: pytest (direct function call)
- **Preconditions**: Empty temp directory (no matching files)
- **Actions**:
  1. Call `resolve_wikilinks("![[nonexistent.png]]", vault_root=temp_dir, temp_dir=temp_dir)`
- **Expected outcome**:
  - Result text contains `[Missing: nonexistent.png]`
  - Resolved count is 0
- **Interactions**: filesystem

### Test 20: ensure_list_spacing inserts blank line before first list item

- **Name**: List spacing fixer inserts blank line when list follows a paragraph directly
- **Type**: regression
- **Disposition**: new
- **Harness**: pytest (direct function call)
- **Preconditions**: None
- **Actions**:
  1. Call `ensure_list_spacing("Some text\n1. First item\n2. Second item")`
- **Expected outcome**:
  - Result is `"Some text\n\n1. First item\n2. Second item"`
  - Blank line inserted before `1.` but not between `1.` and `2.`
- **Interactions**: None (pure function)

### Test 21: ensure_list_spacing does not double-insert blank lines

- **Name**: List spacing fixer is idempotent — no extra blanks if one already exists
- **Type**: regression
- **Disposition**: new
- **Harness**: pytest (direct function call)
- **Preconditions**: None
- **Actions**:
  1. Call `ensure_list_spacing("Some text\n\n- First item\n- Second item")`
- **Expected outcome**:
  - Result is unchanged: `"Some text\n\n- First item\n- Second item"`
  - No additional blank lines inserted
- **Interactions**: None (pure function)

### Test 22: ensure_list_spacing handles bullet lists (-, *, +)

- **Name**: List spacing fixer works for all markdown bullet markers
- **Type**: regression
- **Disposition**: new
- **Harness**: pytest (direct function call)
- **Preconditions**: None
- **Actions**:
  1. For each marker (`-`, `*`, `+`):
     - Call `ensure_list_spacing(f"Text\n{marker} item")`
- **Expected outcome**:
  - Each result has a blank line inserted before the list item
- **Interactions**: None (pure function)

---

## 4. Cross-engine content parity tests (~10% effort)

### Test 23: Same text content extracted from both engine outputs

- **Name**: LaTeX and Typst PDFs from the same source contain the same substantive text
- **Type**: differential
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF text extraction
- **Preconditions**: Both `xelatex`/`pdflatex` and `typst` on PATH; pandoc >= 3.1.7
- **Actions**:
  1. Run `obsidian-to-pdf.py --engine latex "test-vault/Trycycle Overview.md"` -> `latex.pdf`
  2. Run `obsidian-to-pdf.py --engine typst "test-vault/Trycycle Overview.md"` -> `typst.pdf`
  3. Extract text from both PDFs
  4. Normalize whitespace, compare key phrases
- **Expected outcome**:
  - Both contain "Trycycle"
  - Both contain "hill climber"
  - Both contain "Planning"
  - Both contain "Review"
  - Both contain "Dan Shapiro"
  - (Exact whitespace and formatting may differ; compare normalized word sets)
- **Interactions**: pandoc, both engines, PyMuPDF
- **Skip condition**: Skip if either engine unavailable

### Test 24: Table content present in both engine outputs

- **Name**: Tables in markdown render as extractable text in both engines
- **Type**: differential
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF text extraction
- **Preconditions**: Same as Test 23; `test-vault/Trycycle Overview.md` contains a markdown table
- **Actions**:
  1. Generate PDFs with both engines from `Trycycle Overview.md`
  2. Extract text from both
- **Expected outcome**:
  - Both contain table cell content (e.g., "Component", "Role", "Lifecycle" from the table header row)
- **Interactions**: pandoc, both engines, PyMuPDF
- **Skip condition**: Same as Test 23

### Test 25: Footnote content present in both engine outputs

- **Name**: Footnotes in markdown appear in both engine PDFs
- **Type**: differential
- **Disposition**: new
- **Harness**: pytest + subprocess + PyMuPDF text extraction
- **Preconditions**: Same as Test 23; `test-vault/Trycycle Overview.md` contains `[^1]` footnote
- **Actions**:
  1. Generate PDFs with both engines
  2. Extract all text
- **Expected outcome**:
  - Both PDFs contain footnote indicator text (the footnote body text, however rendered)
- **Interactions**: pandoc, both engines, PyMuPDF
- **Skip condition**: Same as Test 23

---

## Test infrastructure notes

### Harness: pytest + subprocess

All end-to-end tests invoke the script as a subprocess, matching real-world usage. This avoids import-time side effects and tests the full CLI path including argparse.

### Skip conditions

Tests requiring specific engines use `pytest.mark.skipif` with `shutil.which()` checks. Tests requiring both engines for differential comparison skip entirely if either is missing.

### Cleanup

End-to-end tests should clean up generated `.pdf` files in a fixture teardown (`yield` fixture or `addFinalizer`). Tests must not leave artifacts in the test vault.

### File organization

All tests go in `test_engines.py` at the repository root. Fixtures for shared setup (engine availability checks, PDF generation helpers, text extraction) should be defined at module level or in a `conftest.py` if the file grows large.

### Parametrization

- Test 6 uses `pytest.mark.parametrize` over the cartesian product of engines and test vault `.md` files.
- Test 22 uses parametrize over bullet markers.

---

## Summary

| Category | Count | Effort |
|---|---|---|
| End-to-end CLI (scenarios) | 7 | ~60% |
| Engine selection & CLI flags (unit/boundary) | 9 | ~20% |
| Regression (existing functions) | 6 | ~10% |
| Cross-engine parity (differential) | 3 | ~10% |
| **Total** | **25** | 100% |
