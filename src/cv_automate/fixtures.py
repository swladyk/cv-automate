"""A tailoring built mechanically from the profile, with no model involved.

Used by the tests, and by ``cv gen --stub``, to exercise the whole render and
compile path offline. It selects everything and rephrases nothing, so it is also
a reasonable "kitchen sink" CV for checking that a template handles every
section.
"""

from __future__ import annotations

from .models import (
    Branding,
    Lang,
    Profile,
    SkillGroup,
    TailoredBullet,
    TailoredCV,
    TailoredEntry,
)

DEFAULT_ACCENT = "#2F5D8C"  # calm slate blue; used when no company colour applies

_CATEGORY_LABELS: dict[str, dict[Lang, str]] = {
    "languages": {"en": "Languages", "pl": "Języki programowania"},
    "data": {"en": "Data", "pl": "Dane"},
    "infrastructure": {"en": "Infrastructure", "pl": "Infrastruktura"},
    "general": {"en": "Other", "pl": "Inne"},
}


def stub_tailoring(profile: Profile, lang: Lang = "en") -> TailoredCV:
    """Select everything in the profile, verbatim."""

    def entries(group) -> list[TailoredEntry]:
        return [
            TailoredEntry(
                source_id=item.id,
                bullets=[
                    TailoredBullet(source_id=b.id, text=b.text.get(lang))
                    for b in item.bullets
                ],
            )
            for item in group
        ]

    groups: dict[str, list[str]] = {}
    for skill in profile.skills:
        groups.setdefault(skill.category, []).append(skill.id)

    return TailoredCV(
        language=lang,
        headline=profile.personal.headline.get(lang),
        summary=profile.summary.get(lang),
        branding=Branding(
            company_name="",
            accent_hex=DEFAULT_ACCENT,
            confidence="low",
            rationale="Stub tailoring; no company involved.",
        ),
        experience=entries(profile.experience),
        education=entries(profile.education),
        projects=entries(profile.projects),
        certificate_ids=[c.id for c in profile.certificates],
        skill_groups=[
            SkillGroup(
                name=_CATEGORY_LABELS.get(cat, {}).get(lang, cat.title()),
                skill_ids=ids,
            )
            for cat, ids in groups.items()
        ],
        match_notes="Stub tailoring: everything selected, nothing rephrased.",
    )
