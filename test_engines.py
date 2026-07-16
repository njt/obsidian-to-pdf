"""
Smoke tests for obsidian-to-pdf.py engine support.

Tests cover:
  - Engine selection / CLI flag logic (unit tests with mocks)
  - Regression tests for existing functions (resolve_wikilinks, ensure_list_spacing)
  - End-to-end CLI tests (subprocess, skip if engines not on PATH)
  - Cross-engine content parity (differential, skip if either engine unavailable)
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "obsidian-to-pdf.py"
TEST_VAULT = SCRIPT_DIR / "test-vault"
FONT_DIR = SCRIPT_DIR / "fonts" / "eb-garamond"

# ---------------------------------------------------------------------------
# Import helpers from the script (for unit tests)
# ---------------------------------------------------------------------------
import importlib.util

_spec = importlib.util.spec_from_file_location("obsidian_to_pdf", str(SCRIPT))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

resolve_wikilinks = _mod.resolve_wikilinks
ensure_list_spacing = _mod.ensure_list_spacing
detect_engine = _mod.detect_engine
check_pandoc_version_for_typst = _mod.check_pandoc_version_for_typst
build_typst_cmd = _mod.build_typst_cmd
build_latex_cmd = _mod.build_latex_cmd

# ---------------------------------------------------------------------------
# Engine availability helpers
# ---------------------------------------------------------------------------
HAS_XELATEX = shutil.which("xelatex") is not None
HAS_PDFLATEX = shutil.which("pdflatex") is not None
HAS_LATEX = HAS_XELATEX or HAS_PDFLATEX
HAS_TYPST = shutil.which("typst") is not None
HAS_PANDOC = shutil.which("pandoc") is not None

skip_no_latex = pytest.mark.skipif(not HAS_LATEX, reason="No LaTeX engine on PATH")
skip_no_typst = pytest.mark.skipif(not HAS_TYPST, reason="typst not on PATH")
skip_no_pandoc = pytest.mark.skipif(not HAS_PANDOC, reason="pandoc not on PATH")
skip_no_both = pytest.mark.skipif(
    not (HAS_LATEX and HAS_TYPST), reason="Need both LaTeX and Typst"
)


def _pandoc_version_ok():
    """Return True if pandoc >= 3.1.7."""
    if not HAS_PANDOC:
        return False
    try:
        import re
        out = subprocess.run(
            ["pandoc", "--version"], capture_output=True, text=True
        ).stdout
        ver = out.splitlines()[0].split()[-1]
        parts = [int(re.match(r'(\d+)', x).group(1)) for x in ver.split(".")]
        return tuple(parts) >= (3, 1, 7)
    except Exception:
        return False


PANDOC_OK_FOR_TYPST = _pandoc_version_ok()
skip_no_typst_full = pytest.mark.skipif(
    not (HAS_TYPST and PANDOC_OK_FOR_TYPST and HAS_PANDOC),
    reason="Typst or pandoc >= 3.1.7 not available",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="test-obsidian-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def cleanup_pdfs():
    """Remove generated PDFs in test-vault after test."""
    yield
    for pdf in TEST_VAULT.glob("*.pdf"):
        pdf.unlink(missing_ok=True)


# ===================================================================
# 2. Engine selection and CLI flag tests (unit tests with mocks)
# ===================================================================


class TestDetectEngine:
    """Tests 8-13: engine detection logic."""

    def test_auto_prefers_latex_when_both_available(self):
        """Test 8: Auto-detection prefers LaTeX over Typst."""
        def fake_which(name):
            return {
                "xelatex": "/usr/local/bin/xelatex",
                "pdflatex": "/usr/local/bin/pdflatex",
                "typst": "/usr/local/bin/typst",
                "pandoc": "/usr/local/bin/pandoc",
            }.get(name)

        with mock.patch("shutil.which", side_effect=fake_which):
            engine, engine_name = detect_engine("auto")
        assert engine == "latex"
        assert engine_name == "xelatex"

    def test_auto_selects_typst_when_no_latex(self):
        """Test 9: Auto-detection falls back to Typst."""
        def fake_which(name):
            return {
                "typst": "/usr/local/bin/typst",
                "pandoc": "/usr/local/bin/pandoc",
            }.get(name)

        with mock.patch("shutil.which", side_effect=fake_which):
            engine, engine_name = detect_engine("auto")
        assert engine == "typst"
        assert engine_name == "typst"

    def test_auto_prefers_xelatex_over_pdflatex(self):
        """Test 10: Auto-detection prefers xelatex over pdflatex."""
        def fake_which(name):
            return {
                "xelatex": "/usr/local/bin/xelatex",
                "pdflatex": "/usr/local/bin/pdflatex",
                "pandoc": "/usr/local/bin/pandoc",
            }.get(name)

        with mock.patch("shutil.which", side_effect=fake_which):
            engine, engine_name = detect_engine("auto")
        assert engine_name == "xelatex"

    def test_auto_errors_when_no_engine(self, capsys):
        """Test 11: Auto-detection errors when no engine found."""
        def fake_which(name):
            if name == "pandoc":
                return "/usr/local/bin/pandoc"
            return None

        with mock.patch("shutil.which", side_effect=fake_which):
            with pytest.raises(SystemExit):
                detect_engine("auto")
        captured = capsys.readouterr()
        assert "brew install typst" in captured.out
        assert "brew install --cask mactex" in captured.out

    def test_explicit_typst_errors_when_missing(self, capsys):
        """Test 12: --engine typst errors when typst not installed."""
        def fake_which(name):
            if name == "pandoc":
                return "/usr/local/bin/pandoc"
            return None

        with mock.patch("shutil.which", side_effect=fake_which):
            with pytest.raises(SystemExit):
                detect_engine("typst")
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_explicit_latex_errors_when_missing(self, capsys):
        """Test 13: --engine latex errors when no LaTeX installed."""
        def fake_which(name):
            if name == "pandoc":
                return "/usr/local/bin/pandoc"
            return None

        with mock.patch("shutil.which", side_effect=fake_which):
            with pytest.raises(SystemExit):
                detect_engine("latex")
        captured = capsys.readouterr()
        assert "no latex engine found" in captured.out.lower()


class TestPandocVersionCheck:
    """Tests 14-15: pandoc version check for Typst."""

    def test_rejects_old_pandoc(self):
        """Test 14: Rejects pandoc < 3.1.7 for Typst."""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "pandoc 3.1.6\nCompiled with pandoc-types..."
        with mock.patch("subprocess.run", return_value=fake_result):
            with pytest.raises(SystemExit):
                check_pandoc_version_for_typst("/usr/local/bin/pandoc")

    def test_accepts_sufficient_pandoc_317(self):
        """Test 15a: Accepts pandoc 3.1.7."""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "pandoc 3.1.7\nCompiled with pandoc-types..."
        with mock.patch("subprocess.run", return_value=fake_result):
            check_pandoc_version_for_typst("/usr/local/bin/pandoc")  # should not raise

    def test_accepts_sufficient_pandoc_350(self):
        """Test 15b: Accepts pandoc 3.5.0."""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "pandoc 3.5.0\nCompiled with pandoc-types..."
        with mock.patch("subprocess.run", return_value=fake_result):
            check_pandoc_version_for_typst("/usr/local/bin/pandoc")  # should not raise

    def test_handles_rc_suffix(self):
        """Test 15c: Handles version strings with non-numeric suffixes like 3.1.7-rc1."""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "pandoc 3.1.7-rc1\nCompiled with pandoc-types..."
        with mock.patch("subprocess.run", return_value=fake_result):
            check_pandoc_version_for_typst("/usr/local/bin/pandoc")  # should not raise

    def test_rejects_old_pandoc_with_rc_suffix(self):
        """Test 15d: Rejects old pandoc even with rc suffix."""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "pandoc 3.1.6-rc2\nCompiled with pandoc-types..."
        with mock.patch("subprocess.run", return_value=fake_result):
            with pytest.raises(SystemExit):
                check_pandoc_version_for_typst("/usr/local/bin/pandoc")

    def test_uses_provided_pandoc_path(self):
        """Test 15e: Uses the provided pandoc path, not bare 'pandoc'."""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "pandoc 3.5.0\nCompiled with pandoc-types..."
        with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            check_pandoc_version_for_typst("/custom/path/pandoc")
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == "/custom/path/pandoc"


class TestInvalidEngine:
    """Test 16: invalid --engine value rejected by argparse."""

    def test_invalid_engine_rejected_any_env(self):
        """Argparse rejects invalid --engine values before any engine check."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--engine", "foobar", "dummy.md"],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr.lower()


# ===================================================================
# 3. Regression tests for existing functions
# ===================================================================


class TestResolveWikilinks:
    """Tests 17-19: wikilink resolution."""

    def test_image_embed(self, tmp_dir):
        """Test 17: ![[image.png]] resolves to standard markdown."""
        img_path = os.path.join(tmp_dir, "photo.png")
        Path(img_path).touch()
        result, count = resolve_wikilinks("Look: ![[photo.png]]", tmp_dir, tmp_dir)
        assert count == 1
        assert f"![](/{tmp_dir}/photo.png)" in result or f"![]({img_path})" in result

    def test_caption_syntax(self, tmp_dir):
        """Test 18: ![[image.png|My Caption]] preserves caption."""
        img_path = os.path.join(tmp_dir, "photo.png")
        Path(img_path).touch()
        result, count = resolve_wikilinks(
            "![[photo.png|A nice photo]]", tmp_dir, tmp_dir
        )
        assert count == 1
        assert "![A nice photo](" in result

    def test_missing_file(self, tmp_dir):
        """Test 19: Missing file gives placeholder text."""
        result, count = resolve_wikilinks("![[nonexistent.png]]", tmp_dir, tmp_dir)
        assert count == 0
        assert "[Missing: nonexistent.png]" in result


class TestEnsureListSpacing:
    """Tests 20-22: list spacing."""

    def test_inserts_blank_before_list(self):
        """Test 20: Inserts blank line before first list item."""
        text = "Some text\n1. First item\n2. Second item"
        result = ensure_list_spacing(text)
        assert result == "Some text\n\n1. First item\n2. Second item"

    def test_idempotent(self):
        """Test 21: No extra blank if one already exists."""
        text = "Some text\n\n- First item\n- Second item"
        result = ensure_list_spacing(text)
        assert result == text

    @pytest.mark.parametrize("marker", ["-", "*", "+"])
    def test_bullet_markers(self, marker):
        """Test 22: Works for all bullet markers."""
        text = f"Text\n{marker} item"
        result = ensure_list_spacing(text)
        assert result == f"Text\n\n{marker} item"


# ===================================================================
# 1. End-to-end CLI tests
# ===================================================================


class TestLatexEndToEnd:
    """Tests 1, 4: LaTeX end-to-end."""

    @skip_no_pandoc
    @skip_no_latex
    def test_latex_produces_pdf(self, cleanup_pdfs):
        """Test 1: LaTeX engine produces valid PDF."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--engine",
                "latex",
                str(TEST_VAULT / "Trycycle Overview.md"),
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        pdf = TEST_VAULT / "Trycycle Overview.pdf"
        assert pdf.exists()
        assert pdf.stat().st_size > 1024
        assert "Using PDF engine:" in result.stdout

    @skip_no_pandoc
    @skip_no_latex
    def test_latex_pdf_content(self, cleanup_pdfs):
        """Test 4: LaTeX PDF contains expected text."""
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--engine",
                "latex",
                str(TEST_VAULT / "Trycycle Overview.md"),
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        pdf = TEST_VAULT / "Trycycle Overview.pdf"
        if not pdf.exists():
            pytest.skip("PDF not generated")
        import fitz

        doc = fitz.open(str(pdf))
        text = "".join(page.get_text() for page in doc)
        doc.close()
        assert "Trycycle" in text
        assert "hill climber" in text.lower() or "hill-climber" in text.lower()
        assert "Planning" in text or "planning" in text


class TestTypstEndToEnd:
    """Tests 2, 3, 5, 7: Typst end-to-end."""

    @skip_no_pandoc
    @skip_no_typst_full
    def test_typst_produces_pdf(self, cleanup_pdfs):
        """Test 2: Typst engine produces valid PDF."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--engine",
                "typst",
                str(TEST_VAULT / "Trycycle Overview.md"),
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        pdf = TEST_VAULT / "Trycycle Overview.pdf"
        assert pdf.exists()
        assert pdf.stat().st_size > 1024
        assert "Using PDF engine:" in result.stdout
        assert "typst" in result.stdout.lower()

    @skip_no_pandoc
    @skip_no_typst_full
    def test_typst_pdf_content(self, cleanup_pdfs):
        """Test 3: Typst PDF contains expected text."""
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--engine",
                "typst",
                str(TEST_VAULT / "Trycycle Overview.md"),
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        pdf = TEST_VAULT / "Trycycle Overview.pdf"
        if not pdf.exists():
            pytest.skip("PDF not generated")
        import fitz

        doc = fitz.open(str(pdf))
        text = "".join(page.get_text() for page in doc)
        doc.close()
        assert "Trycycle" in text
        assert "hill climber" in text.lower() or "hill-climber" in text.lower()
        assert "Planning" in text or "planning" in text

    @skip_no_pandoc
    @skip_no_typst_full
    def test_typst_pdf_uses_eb_garamond(self, cleanup_pdfs):
        """Test 5: Typst PDF embeds EB Garamond font."""
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--engine",
                "typst",
                str(TEST_VAULT / "Trycycle Overview.md"),
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        pdf = TEST_VAULT / "Trycycle Overview.pdf"
        if not pdf.exists():
            pytest.skip("PDF not generated")
        import fitz

        doc = fitz.open(str(pdf))
        fonts = set()
        for page in doc:
            for f in page.get_fonts():
                fonts.add(f[3])  # font name field
        doc.close()
        assert any("garamond" in fn.lower() for fn in fonts), f"Fonts found: {fonts}"

    @skip_no_pandoc
    @skip_no_typst_full
    def test_typst_wikilink_image(self, cleanup_pdfs):
        """Test 7: Wikilink image embedding works in Typst output."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--engine",
                "typst",
                str(TEST_VAULT / "Superpowers.md"),
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Resolved 1 image(s)" in result.stdout
        pdf = TEST_VAULT / "Superpowers.pdf"
        assert pdf.exists()
        # Check for embedded image
        import fitz

        doc = fitz.open(str(pdf))
        images = doc[0].get_images() if len(doc) > 0 else []
        doc.close()
        assert len(images) >= 1, "Expected at least one image on page 1"


class TestAllVaultFiles:
    """Test 6: All test vault files produce PDFs with each engine."""

    @staticmethod
    def _vault_md_files():
        return sorted(TEST_VAULT.glob("*.md"))

    @skip_no_pandoc
    @skip_no_latex
    @pytest.mark.parametrize(
        "md_file",
        sorted((TEST_VAULT).glob("*.md")),
        ids=lambda p: p.name,
    )
    def test_latex_all_vault(self, md_file, cleanup_pdfs):
        """Test 6 (latex): Every md file converts with LaTeX."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--engine", "latex", str(md_file)],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        assert result.returncode == 0, f"Failed: {md_file.name}\nstderr: {result.stderr}"
        pdf = md_file.with_suffix(".pdf")
        assert pdf.exists()
        assert pdf.stat().st_size > 1024

    @skip_no_pandoc
    @skip_no_typst_full
    @pytest.mark.parametrize(
        "md_file",
        sorted((TEST_VAULT).glob("*.md")),
        ids=lambda p: p.name,
    )
    def test_typst_all_vault(self, md_file, cleanup_pdfs):
        """Test 6 (typst): Every md file converts with Typst."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--engine", "typst", str(md_file)],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        assert result.returncode == 0, f"Failed: {md_file.name}\nstderr: {result.stderr}"
        pdf = md_file.with_suffix(".pdf")
        assert pdf.exists()
        assert pdf.stat().st_size > 1024


# ===================================================================
# 4. Cross-engine content parity tests
# ===================================================================


class TestCrossEngineParity:
    """Tests 23-25: Same content from both engines."""

    @skip_no_pandoc
    @skip_no_both
    @pytest.mark.skipif(not PANDOC_OK_FOR_TYPST, reason="pandoc < 3.1.7")
    def test_same_text_content(self, cleanup_pdfs, tmp_dir):
        """Test 23: Both engines produce PDFs with same substantive text."""
        md_src = TEST_VAULT / "Trycycle Overview.md"
        import fitz

        texts = {}
        for engine in ("latex", "typst"):
            # Copy md to engine-specific temp file so outputs don't collide
            engine_md = os.path.join(tmp_dir, f"Trycycle Overview_{engine}.md")
            shutil.copy2(str(md_src), engine_md)
            engine_pdf = os.path.splitext(engine_md)[0] + ".pdf"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--engine", engine, engine_md],
                capture_output=True,
                text=True,
                cwd=str(SCRIPT_DIR),
            )
            if not os.path.exists(engine_pdf):
                pytest.skip(f"PDF not generated for {engine}")
            doc = fitz.open(engine_pdf)
            texts[engine] = "".join(page.get_text() for page in doc)
            doc.close()

        for phrase in ["Trycycle", "hill climber", "Planning", "Review", "Dan Shapiro"]:
            for eng, text in texts.items():
                assert phrase.lower() in text.lower(), (
                    f"'{phrase}' not found in {eng} output"
                )

    @skip_no_pandoc
    @skip_no_both
    @pytest.mark.skipif(not PANDOC_OK_FOR_TYPST, reason="pandoc < 3.1.7")
    def test_table_content_both(self, cleanup_pdfs, tmp_dir):
        """Test 24: Table content present in both engine outputs."""
        md_src = TEST_VAULT / "Trycycle Overview.md"
        import fitz

        for engine in ("latex", "typst"):
            engine_md = os.path.join(tmp_dir, f"Trycycle Overview_{engine}.md")
            shutil.copy2(str(md_src), engine_md)
            engine_pdf = os.path.splitext(engine_md)[0] + ".pdf"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--engine", engine, engine_md],
                capture_output=True,
                text=True,
                cwd=str(SCRIPT_DIR),
            )
            doc = fitz.open(engine_pdf)
            text = "".join(page.get_text() for page in doc).lower()
            doc.close()
            assert "component" in text or "role" in text, (
                f"Table content not found in {engine} output"
            )

    @skip_no_pandoc
    @skip_no_both
    @pytest.mark.skipif(not PANDOC_OK_FOR_TYPST, reason="pandoc < 3.1.7")
    def test_footnote_content_both(self, cleanup_pdfs, tmp_dir):
        """Test 25: Footnote content present in both engine outputs."""
        md_src = TEST_VAULT / "Trycycle Overview.md"
        import fitz

        for engine in ("latex", "typst"):
            engine_md = os.path.join(tmp_dir, f"Trycycle Overview_{engine}.md")
            shutil.copy2(str(md_src), engine_md)
            engine_pdf = os.path.splitext(engine_md)[0] + ".pdf"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--engine", engine, engine_md],
                capture_output=True,
                text=True,
                cwd=str(SCRIPT_DIR),
            )
            if not os.path.exists(engine_pdf):
                pytest.skip(f"PDF not generated for {engine}")
            doc = fitz.open(engine_pdf)
            text = "".join(page.get_text() for page in doc)
            doc.close()
            # Footnote body text should appear somewhere in the PDF
            assert "strongdm" in text.lower(), (
                f"Footnote body text 'StrongDM' not found in {engine} output"
            )
