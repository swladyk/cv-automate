"""Make a company's brand colour safe to print on a CV.

Brand colours are chosen for logos and websites, not for 10pt text on white
paper. Bright yellow, neon green and near-white all look fine on a billboard and
are unreadable as a heading. This module takes a proposed colour and returns one
that is recognisably the same hue but actually legible.

The work happens in OKLCh rather than RGB: darkening in RGB desaturates and
muddies a colour, while dropping lightness in OKLCh keeps the hue exactly and
looks like the same brand colour, just deeper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# WCAG AA for normal-size text. Accent is only used on headings and rules, which
# are larger, so this is deliberately stricter than strictly required.
MIN_CONTRAST = 4.5

# Below this chroma a colour is grey/near-white/near-black: there is no hue worth
# preserving, so it makes a poor accent and we fall back to the default.
MIN_CHROMA = 0.03

_WHITE_LUMINANCE = 1.0


# --------------------------------------------------------------------------
# sRGB
# --------------------------------------------------------------------------


def parse_hex(value: str) -> tuple[float, float, float]:
    """``#RRGGBB`` (or ``RRGGBB``, or ``#RGB``) to 0..1 floats."""
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6 or any(c not in "0123456789abcdefABCDEF" for c in v):
        raise ValueError(f"not a hex colour: {value!r}")
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _linearize(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _delinearize(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_linearize(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_on_white(rgb: tuple[float, float, float]) -> float:
    """WCAG contrast ratio against a white page. 1.0 = invisible, 21.0 = black."""
    return (_WHITE_LUMINANCE + 0.05) / (relative_luminance(rgb) + 0.05)


# --------------------------------------------------------------------------
# OKLab / OKLCh  (Björn Ottosson's matrices)
# --------------------------------------------------------------------------


def rgb_to_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_linearize(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = (v**3 for v in (l_, m_, s_))
    return (
        _delinearize(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        _delinearize(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        _delinearize(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def rgb_to_oklch(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = rgb_to_oklab(rgb)
    chroma = math.hypot(a, b)
    hue = math.degrees(math.atan2(b, a)) % 360
    return L, chroma, hue


def oklch_to_rgb(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    L, chroma, hue = lch
    rad = math.radians(hue)
    return oklab_to_rgb((L, chroma * math.cos(rad), chroma * math.sin(rad)))


def _in_gamut(rgb: tuple[float, float, float], eps: float = 1e-4) -> bool:
    return all(-eps <= c <= 1 + eps for c in rgb)


def _gamut_map(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    """Pull a colour into sRGB by reducing chroma, never by clipping channels.

    Clipping RGB channels shifts the hue, which is the one property worth
    protecting here — the whole point is that it still looks like their colour.
    """
    L, chroma, hue = lch
    rgb = oklch_to_rgb(lch)
    if _in_gamut(rgb):
        return tuple(min(1.0, max(0.0, c)) for c in rgb)  # type: ignore[return-value]

    lo, hi = 0.0, chroma
    for _ in range(40):
        mid = (lo + hi) / 2
        if _in_gamut(oklch_to_rgb((L, mid, hue))):
            lo = mid
        else:
            hi = mid
    rgb = oklch_to_rgb((L, lo, hue))
    return tuple(min(1.0, max(0.0, c)) for c in rgb)  # type: ignore[return-value]


# --------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------


@dataclass
class AccentDecision:
    hex: str
    """The colour to actually use, always legible."""
    original: str
    """What was proposed, for reporting."""
    action: str
    """One of: ``kept``, ``darkened``, ``too-neutral``, ``invalid``, ``low-confidence``."""
    note: str
    """One line suitable for printing to the user."""

    @property
    def changed(self) -> bool:
        return self.hex.upper() != self.original.upper()


def clamp_accent(
    proposed: str,
    default: str,
    min_contrast: float = MIN_CONTRAST,
    min_chroma: float = MIN_CHROMA,
) -> AccentDecision:
    """Return a legible accent close to ``proposed``, or ``default`` if it can't be.

    Darkening keeps hue exactly and only reduces lightness, so the result still
    reads as the company's colour.
    """
    try:
        rgb = parse_hex(proposed)
    except ValueError:
        return AccentDecision(
            hex=to_hex(parse_hex(default)),
            original=proposed,
            action="invalid",
            note=f"{proposed!r} is not a valid colour; using your default accent.",
        )

    L, chroma, hue = rgb_to_oklch(rgb)

    if chroma < min_chroma:
        return AccentDecision(
            hex=to_hex(parse_hex(default)),
            original=to_hex(rgb),
            action="too-neutral",
            note=(
                f"{to_hex(rgb)} is essentially greyscale, which makes a poor accent; "
                "using your default."
            ),
        )

    if contrast_on_white(rgb) >= min_contrast:
        return AccentDecision(
            hex=to_hex(rgb), original=to_hex(rgb), action="kept", note=""
        )

    # Walk lightness down, keeping hue fixed and letting the gamut mapper give up
    # chroma where it must. Black is 21:1, so this always terminates in range.
    step = 0.005
    lightness = L
    while lightness > 0:
        lightness = max(0.0, lightness - step)
        candidate_hex = to_hex(_gamut_map((lightness, chroma, hue)))
        # Check the colour *after* quantising to 8-bit — that is what actually
        # ships, and rounding can drop it back under the threshold.
        if contrast_on_white(parse_hex(candidate_hex)) >= min_contrast:
            return AccentDecision(
                hex=candidate_hex,
                original=to_hex(rgb),
                action="darkened",
                note=(
                    f"{to_hex(rgb)} is too light to read on white "
                    f"({contrast_on_white(rgb):.1f}:1); darkened to {candidate_hex}."
                ),
            )

    return AccentDecision(
        hex=to_hex(parse_hex(default)),
        original=to_hex(rgb),
        action="too-neutral",
        note=f"Could not make {to_hex(rgb)} legible; using your default accent.",
    )


def resolve_accent(
    proposed: str,
    confidence: str,
    default: str,
    override: str | None = None,
) -> AccentDecision:
    """Decide the final accent from the model's proposal, honouring an override.

    A low-confidence guess is discarded rather than printed: better a neutral CV
    than a confidently wrong shade of someone else's brand.
    """
    if override is not None:
        return clamp_accent(override, default)
    if confidence != "high":
        return AccentDecision(
            hex=to_hex(parse_hex(default)),
            original=proposed,
            action="low-confidence",
            note=(
                "Couldn't confidently identify the company's brand colour, so the CV uses "
                "your default. Pass --accent '#RRGGBB' if you know it."
            ),
        )
    return clamp_accent(proposed, default)
