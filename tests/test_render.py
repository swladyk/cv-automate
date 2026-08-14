"""End-to-end: profile -> LaTeX -> PDF -> extracted text.

The compile tests need a TeX installation, so they skip cleanly without one.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cv_automate.color import clamp_accent
from cv_automate.compile import overfull_warnings, pdf_to_text
from cv_automate.fixtures import DEFAULT_ACCENT, stub_tailoring
from cv_automate.models import TailoredBullet, TailoredEntry
from cv_automate.pipeline import build_cv
from cv_automate.profile import (
    TailoringError,
    build_index,
    load_profile,
    validate_tailoring,
)
from cv_automate.render import latex_escape

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "data" / "profile.example.yaml"

needs_latex = pytest.mark.skipif(
    shutil.which("latexmk") is None, reason="needs a TeX installation"
)
needs_poppler = pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="needs poppler's pdftotext"
)

POLISH_ALPHABET = "ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż"

# Strings that break a naive LaTeX pipeline. These live in the example profile
# too, but pinning them here means a template change can't quietly drop one.
HOSTILE_TEXT = ["R&D", "50% growth", "C++", "$100k", "foo_bar"]


@pytest.fixture(scope="session")
def profile():
    return load_profile(EXAMPLE)


@pytest.fixture(scope="session")
def accent():
    return clamp_accent(DEFAULT_ACCENT, DEFAULT_ACCENT)


# --------------------------------------------------------------------------
# Escaping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("R&D", r"R\&D"),
        ("50%", r"50\%"),
        ("$100k", r"\$100k"),
        ("foo_bar", r"foo\_bar"),
        ("a#b", r"a\#b"),
        ("{x}", r"\{x\}"),
        ("a~b", r"a\textasciitilde{}b"),
        ("2^10", r"2\textasciicircum{}10"),
        # A backslash must not have its replacement re-escaped by a later pass.
        ("a\\b", r"a\textbackslash{}b"),
        ("Zażółć gęślą jaźń", "Zażółć gęślą jaźń"),  # unicode passes through
    ],
)
def test_latex_escape(raw: str, expected: str) -> None:
    assert latex_escape(raw) == expected


# --------------------------------------------------------------------------
# The no-invention guard
# --------------------------------------------------------------------------


def test_unknown_source_id_is_rejected(profile) -> None:
    """The central guarantee: content with no basis in the profile never renders."""
    index = build_index(profile)
    tailored = stub_tailoring(profile, "en")
    tailored.experience.append(
        TailoredEntry(
            source_id="exp-does-not-exist",
            bullets=[TailoredBullet(source_id="exp-does-not-exist-b1", text="Ran NASA.")],
        )
    )
    with pytest.raises(TailoringError) as excinfo:
        validate_tailoring(tailored, index)
    assert "exp-does-not-exist" in str(excinfo.value)


def test_unknown_skill_id_is_rejected(profile) -> None:
    index = build_index(profile)
    tailored = stub_tailoring(profile, "en")
    tailored.skill_groups[0].skill_ids.append("skill-rust")
    with pytest.raises(TailoringError) as excinfo:
        validate_tailoring(tailored, index)
    assert "skill-rust" in str(excinfo.value)


def test_stub_tailoring_is_valid(profile) -> None:
    validate_tailoring(stub_tailoring(profile, "en"), build_index(profile))


# --------------------------------------------------------------------------
# Compile
# --------------------------------------------------------------------------


@needs_latex
@pytest.mark.parametrize("lang", ["en", "pl"])
@pytest.mark.parametrize("variant", ["ats", "designed"])
def test_every_variant_compiles(profile, accent, tmp_path, lang, variant) -> None:
    built = build_cv(
        profile, stub_tailoring(profile, lang), lang, variant, accent, tmp_path, repo_root=REPO
    )
    assert built.pdf.exists() and built.pdf.stat().st_size > 1000


@needs_latex
@needs_poppler
def test_ats_text_survives_extraction(profile, accent, tmp_path) -> None:
    """The whole point of the ATS variant: a parser can read it back."""
    built = build_cv(
        profile, stub_tailoring(profile, "en"), "en", "ats", accent, tmp_path, repo_root=REPO
    )
    text = pdf_to_text(built.pdf)

    for fragment in HOSTILE_TEXT:
        assert fragment in text, f"{fragment!r} did not survive to the PDF"

    assert profile.personal.full_name in text
    assert profile.personal.email in text

    # Assert on order of appearance, not on each heading sitting alone on its
    # own extracted line — that depends on how pdftotext happens to lay out the
    # page, which shifts with content density and is not what we care about.
    expected = ["Profile", "Experience", "Education", "Projects", "Certificates", "Skills", "Languages"]
    positions = []
    for heading in expected:
        at = text.find(heading)
        assert at >= 0, f"section {heading!r} is missing from the extracted text"
        positions.append(at)
    assert positions == sorted(positions), (
        "sections do not extract in reading order: "
        + ", ".join(f"{h}@{p}" for h, p in zip(expected, positions))
    )


@needs_latex
@needs_poppler
@pytest.mark.parametrize("variant", ["ats", "designed"])
def test_polish_alphabet_survives_roundtrip(profile, accent, tmp_path, variant) -> None:
    """Catches a wrong font or a missing polyglossia setup immediately."""
    tailored = stub_tailoring(profile, "pl")
    tailored.summary = POLISH_ALPHABET
    built = build_cv(profile, tailored, "pl", variant, accent, tmp_path, repo_root=REPO)
    text = pdf_to_text(built.pdf)
    for char in POLISH_ALPHABET.replace(" ", ""):
        assert char in text, f"{char!r} did not survive to the PDF"


@needs_latex
@needs_poppler
def test_accent_colour_does_not_affect_extracted_text(profile, tmp_path) -> None:
    """Colour is presentation only; a parser must see the same words either way."""
    tailored = stub_tailoring(profile, "en")
    neutral = clamp_accent(DEFAULT_ACCENT, DEFAULT_ACCENT)
    branded = clamp_accent("#1DB954", DEFAULT_ACCENT)

    a = build_cv(profile, tailored, "en", "designed", neutral, tmp_path / "a", repo_root=REPO)
    b = build_cv(profile, tailored, "en", "designed", branded, tmp_path / "b", repo_root=REPO)
    assert pdf_to_text(a.pdf) == pdf_to_text(b.pdf)


@needs_latex
def test_missing_photo_warns_instead_of_failing(profile, accent, tmp_path) -> None:
    """A missing photo should degrade to a photo-less CV, not a crash."""
    profile = profile.model_copy(deep=True)
    profile.personal.photo = "data/assets/definitely-not-here.jpg"
    built = build_cv(
        profile, stub_tailoring(profile, "en"), "en", "designed", accent, tmp_path, repo_root=REPO
    )
    assert built.pdf.exists()
    assert any("Photo not found" in w for w in built.warnings)


def test_overfull_warning_parsing() -> None:
    """Text spilling past the margin is a layout bug you can't see in the source."""
    log = (
        r"Overfull \hbox (23.4pt too wide) in paragraph at lines 12--14" "\n"
        r"Overfull \hbox (0.9pt too wide) in paragraph at lines 20--21" "\n"
    )
    warnings = overfull_warnings(log)
    assert len(warnings) == 1, "sub-threshold overfulls are noise and must be dropped"
    assert "23pt" in warnings[0]


@needs_latex
@pytest.mark.parametrize("lang", ["en", "pl"])
@pytest.mark.parametrize("variant", ["ats", "designed"])
def test_no_text_runs_off_the_page(profile, accent, tmp_path, lang, variant) -> None:
    built = build_cv(
        profile, stub_tailoring(profile, lang), lang, variant, accent, tmp_path, repo_root=REPO
    )
    spills = [w for w in built.warnings if "past the margin" in w]
    assert not spills, "\n".join(spills)
