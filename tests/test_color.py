"""The accent clamp has one job: never emit an illegible colour."""

from __future__ import annotations

import pytest

from cv_automate.color import (
    MIN_CONTRAST,
    clamp_accent,
    contrast_on_white,
    oklch_to_rgb,
    parse_hex,
    resolve_accent,
    rgb_to_oklch,
    to_hex,
)

DEFAULT = "#2F5D8C"

# Real brand-ish colours that are hostile in different ways.
HOSTILE = [
    "#FFFF00",  # pure yellow — the classic unreadable-on-white case
    "#00FF00",  # neon green
    "#FAFAFA",  # near-white
    "#808080",  # mid grey
    "#FFFFFF",  # white
    "#00E5FF",  # bright cyan
    "#FFD700",  # gold
    "#FF69B4",  # hot pink
]


@pytest.mark.parametrize("proposed", HOSTILE)
def test_never_returns_an_illegible_colour(proposed: str) -> None:
    decision = clamp_accent(proposed, DEFAULT)
    assert contrast_on_white(parse_hex(decision.hex)) >= MIN_CONTRAST


@pytest.mark.parametrize("proposed", ["#FAFAFA", "#808080", "#FFFFFF"])
def test_greyscale_falls_back_to_default(proposed: str) -> None:
    decision = clamp_accent(proposed, DEFAULT)
    assert decision.hex == DEFAULT
    assert decision.action == "too-neutral"


@pytest.mark.parametrize("proposed", ["#FFFF00", "#00FF00", "#00E5FF", "#FF69B4"])
def test_darkening_preserves_hue(proposed: str) -> None:
    """A darkened brand colour must still read as the same colour."""
    decision = clamp_accent(proposed, DEFAULT)
    assert decision.action == "darkened"
    _, _, hue_before = rgb_to_oklch(parse_hex(proposed))
    _, _, hue_after = rgb_to_oklch(parse_hex(decision.hex))
    drift = abs((hue_after - hue_before + 180) % 360 - 180)
    assert drift < 3.0, f"hue drifted {drift:.1f}° for {proposed}"


def test_already_legible_colour_is_untouched() -> None:
    decision = clamp_accent("#1A4F8B", DEFAULT)
    assert decision.action == "kept"
    assert decision.hex == "#1A4F8B"
    assert not decision.changed


def test_invalid_input_falls_back_rather_than_raising() -> None:
    decision = clamp_accent("not-a-colour", DEFAULT)
    assert decision.hex == DEFAULT
    assert decision.action == "invalid"


def test_low_confidence_guess_is_discarded() -> None:
    """A plausible-but-unverified colour must not silently reach the CV."""
    decision = resolve_accent("#FF6B00", confidence="low", default=DEFAULT)
    assert decision.hex == DEFAULT
    assert decision.action == "low-confidence"


def test_override_beats_the_model_but_still_gets_clamped() -> None:
    decision = resolve_accent("#123456", confidence="high", default=DEFAULT, override="#FFFF00")
    assert decision.action == "darkened"
    assert contrast_on_white(parse_hex(decision.hex)) >= MIN_CONTRAST


def test_high_confidence_colour_is_used() -> None:
    decision = resolve_accent("#1A4F8B", confidence="high", default=DEFAULT)
    assert decision.hex == "#1A4F8B"


def test_oklch_roundtrip() -> None:
    for hex_in in ["#2F5D8C", "#FFFF00", "#123456", "#E10600"]:
        rgb = parse_hex(hex_in)
        assert to_hex(oklch_to_rgb(rgb_to_oklch(rgb))) == hex_in
