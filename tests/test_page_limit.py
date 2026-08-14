"""The one-page limit.

A model can't see how long its output renders, so the limit is held by
typesetting, measuring, and asking again. These cover both halves: that the
templates fit a realistic CV on one page, and that the retry loop converges.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cv_automate.color import clamp_accent
from cv_automate.fixtures import DEFAULT_ACCENT, stub_tailoring
from cv_automate.models import TailoredCV
from cv_automate.pipeline import DEFAULT_MAX_PAGES, build_cv
from cv_automate.profile import load_profile
from cv_automate.tailor import Overflow

REPO = Path(__file__).resolve().parents[1]

needs_latex = pytest.mark.skipif(
    shutil.which("latexmk") is None, reason="needs a TeX installation"
)


@pytest.fixture(scope="session")
def profile():
    return load_profile(REPO / "data" / "profile.example.yaml")


@pytest.fixture(scope="session")
def accent():
    return clamp_accent(DEFAULT_ACCENT, DEFAULT_ACCENT)


def budgeted(profile, lang: str = "en") -> TailoredCV:
    """A tailoring at exactly the budget the prompt tells the model to hit.

    3 roles at 4/3/2 bullets, one project, two certificates, three skill groups.
    """
    t = stub_tailoring(profile, lang)
    t.experience = t.experience[:3]
    for i, entry in enumerate(t.experience):
        entry.bullets = entry.bullets[: max(0, 4 - i)]
    for entry in t.education:
        entry.bullets = []
    t.projects = t.projects[:1]
    t.certificate_ids = t.certificate_ids[:2]
    t.skill_groups = t.skill_groups[:3]
    return t


# --------------------------------------------------------------------------
# The templates must actually fit the budget the prompt asks for
# --------------------------------------------------------------------------


@needs_latex
@pytest.mark.parametrize("lang", ["en", "pl"])
@pytest.mark.parametrize("variant", ["ats", "designed"])
def test_a_budgeted_cv_fits_one_page(profile, accent, tmp_path, lang, variant) -> None:
    """If this fails, the prompt is asking for more than the template can hold.

    Fix the template density rather than the budget — a CV cut to three bullets
    to satisfy a loose layout is a worse CV.
    """
    built = build_cv(profile, budgeted(profile, lang), lang, variant, accent, tmp_path, repo_root=REPO)
    assert built.pages == 1, (
        f"{variant}/{lang} came to {built.pages} pages at the documented budget"
    )
    assert not built.overflows(DEFAULT_MAX_PAGES)


@needs_latex
def test_the_stub_overflows_and_is_detected(profile, accent, tmp_path) -> None:
    """The kitchen-sink stub is over budget by design; the check must catch it."""
    built = build_cv(
        profile, stub_tailoring(profile, "en"), "en", "ats", accent, tmp_path, repo_root=REPO
    )
    assert built.pages > 1
    assert built.overflows(DEFAULT_MAX_PAGES)


# --------------------------------------------------------------------------
# The feedback sent back to the model
# --------------------------------------------------------------------------


def test_overflow_feedback_carries_the_real_numbers(profile) -> None:
    previous = stub_tailoring(profile, "en")
    prompt = Overflow(pages=2, max_pages=1, previous=previous).as_prompt()

    assert "2 pages" in prompt
    bullets = sum(len(e.bullets) for e in [*previous.experience, *previous.education, *previous.projects])
    assert str(bullets) in prompt
    # It must say what to cut and in what order, not just "make it shorter".
    assert "projects first" in prompt
    # Dropping whole bullets keeps the survivors readable; squeezing wording doesn't.
    assert "Do not shorten the wording" in prompt


def test_overflow_asks_for_a_proportionate_cut(profile) -> None:
    """A 3-page result should ask for a bigger cut than a 2-page one."""
    previous = stub_tailoring(profile, "en")
    two = Overflow(pages=2, max_pages=1, previous=previous).as_prompt()
    three = Overflow(pages=3, max_pages=1, previous=previous).as_prompt()

    def cut(text: str) -> int:
        return int(text.split("Cut roughly ")[1].split(" ")[0])

    assert cut(three) > cut(two)


# --------------------------------------------------------------------------
# The retry loop
# --------------------------------------------------------------------------


@needs_latex
def test_retry_loop_converges(profile, accent, tmp_path, monkeypatch) -> None:
    """Over-long first attempt, budgeted second: the loop must take the second."""
    attempts: list[Overflow | None] = []

    def fake_tailor(prof, job, lang, client=None, model="", overflow=None):
        from cv_automate.tailor import TailorResult

        attempts.append(overflow)
        tailoring = stub_tailoring(prof, lang) if overflow is None else budgeted(prof, lang)
        return TailorResult(tailoring=tailoring, input_tokens=1, output_tokens=1, cache_read_tokens=0)

    monkeypatch.setattr("cv_automate.cli.tailor", fake_tailor)

    from typer.testing import CliRunner

    from cv_automate.cli import app

    posting = tmp_path / "acme-engineer.md"
    posting.write_text("Senior Data Engineer at Acme. Python, Airflow. " * 5, encoding="utf-8")

    monkeypatch.chdir(REPO)
    result = CliRunner().invoke(
        app,
        ["gen", str(posting), "--lang", "en", "--out", str(tmp_path / "out")],
    )

    assert result.exit_code == 0, result.output
    assert len(attempts) == 2, f"expected one retry, got {len(attempts)} attempts"
    assert attempts[0] is None and attempts[1] is not None
    assert attempts[1].pages == 2

    from cv_automate.compile import page_count

    for variant in ("ats", "designed"):
        pdf = tmp_path / "out" / "acme-engineer" / "en" / f"cv-{variant}.pdf"
        assert page_count(pdf) == 1, f"{variant} still overflows after the retry"


@needs_latex
def test_no_retry_when_the_first_attempt_fits(profile, tmp_path, monkeypatch) -> None:
    """The retry costs a second API call, so it must not fire needlessly."""
    calls = []

    def fake_tailor(prof, job, lang, client=None, model="", overflow=None):
        from cv_automate.tailor import TailorResult

        calls.append(overflow)
        return TailorResult(
            tailoring=budgeted(prof, lang), input_tokens=1, output_tokens=1, cache_read_tokens=0
        )

    monkeypatch.setattr("cv_automate.cli.tailor", fake_tailor)

    from typer.testing import CliRunner

    from cv_automate.cli import app

    posting = tmp_path / "acme-engineer.md"
    posting.write_text("Senior Data Engineer at Acme. Python, Airflow. " * 5, encoding="utf-8")

    monkeypatch.chdir(REPO)
    result = CliRunner().invoke(
        app, ["gen", str(posting), "--lang", "en", "--out", str(tmp_path / "out")]
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1, "retried even though the first attempt fitted"
