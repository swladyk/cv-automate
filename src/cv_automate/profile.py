"""Load the master profile and police what the model is allowed to say.

The id index built here is the backstop for the project's central guarantee: the
model may select, reorder and rephrase, but it may not add facts. Anything it
emits has to trace back to an id that exists in ``profile.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import yaml

from .models import Profile, TailoredCV


class ProfileError(Exception):
    """profile.yaml is malformed."""


class TailoringError(Exception):
    """A tailoring referenced something that does not exist in the profile."""


def load_profile(path: str | Path) -> Profile:
    path = Path(path)
    if not path.exists():
        raise ProfileError(
            f"No profile at {path}. Run `cv init` to scaffold one from the example."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProfileError(f"{path} should contain a mapping at the top level.")

    profile = Profile.model_validate(raw)
    _reject_duplicate_ids(profile)
    return profile


def _walk_ids(profile: Profile) -> Iterator[tuple[str, Any]]:
    """Yield every (id, item) pair in the profile, bullets included."""
    for link in profile.personal.links:
        yield link.id, link
    for group in (profile.experience, profile.education, profile.projects):
        for entry in group:
            yield entry.id, entry
            for bullet in entry.bullets:
                yield bullet.id, bullet
    for cert in profile.certificates:
        yield cert.id, cert
    for skill in profile.skills:
        yield skill.id, skill
    for lang in profile.languages:
        yield lang.id, lang


def _reject_duplicate_ids(profile: Profile) -> None:
    """A duplicate id would make source validation meaningless, so fail loudly."""
    seen: set[str] = set()
    dupes: list[str] = []
    for item_id, _ in _walk_ids(profile):
        if item_id in seen:
            dupes.append(item_id)
        seen.add(item_id)
    if dupes:
        raise ProfileError(
            "Duplicate ids in profile.yaml: " + ", ".join(sorted(set(dupes)))
        )


def build_index(profile: Profile) -> dict[str, Any]:
    """Map every id in the profile to the object it names."""
    return dict(_walk_ids(profile))


def referenced_ids(tailored: TailoredCV) -> Iterator[str]:
    """Every profile id a tailoring claims to draw on."""
    for group in (tailored.experience, tailored.education, tailored.projects):
        for entry in group:
            yield entry.source_id
            for bullet in entry.bullets:
                yield bullet.source_id
    yield from tailored.certificate_ids
    for skill_group in tailored.skill_groups:
        yield from skill_group.skill_ids


def unknown_source_ids(tailored: TailoredCV, index: dict[str, Any]) -> list[str]:
    return sorted({ref for ref in referenced_ids(tailored) if ref not in index})


def validate_tailoring(tailored: TailoredCV, index: dict[str, Any]) -> None:
    """Reject a tailoring that references anything not in the profile.

    This is what stops an invented job, certificate or bullet from reaching a
    PDF — whether the model hallucinated it or a job posting tried to inject it.
    """
    unknown = unknown_source_ids(tailored, index)
    if unknown:
        raise TailoringError(
            "This tailoring refers to entries that do not exist in your profile, so it was "
            "rejected rather than written to a CV.\n  Unknown ids: "
            + ", ".join(unknown)
            + "\nEither the model invented content, or the job posting tried to inject it."
        )


def unreferenced_ids(profile: Profile) -> list[str]:
    """Profile ids no bullet or entry hangs off — usually just a typo check."""
    index = build_index(profile)
    used: set[str] = set()
    for group in (profile.experience, profile.education, profile.projects):
        for entry in group:
            used.add(entry.id)
            used.update(b.id for b in entry.bullets)
    used.update(c.id for c in profile.certificates)
    used.update(s.id for s in profile.skills)
    used.update(lang.id for lang in profile.languages)
    used.update(link.id for link in profile.personal.links)
    return sorted(set(index) - used)
