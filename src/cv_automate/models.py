"""Schemas for the master profile and for the model's per-job tailoring.

Two families live here:

* **Profile** — what you write by hand in ``data/profile.yaml``. Every list item
  carries a stable ``id``; those ids are the vocabulary the model is allowed to
  draw from.
* **TailoredCV** — what the model returns for one job posting. Every piece of
  rendered prose points back at a profile ``id`` via ``source_id``, so a
  tailoring can be mechanically checked for invented content.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

Lang = Literal["en", "pl"]
LANGUAGES: tuple[Lang, ...] = ("en", "pl")


class Localized(RootModel[str | dict[str, str]]):
    """A string that may be written once, or per language.

    In YAML both of these are valid::

        title: Data Engineer
        title: {en: Data Engineer, pl: Inżynier Danych}

    ``get()`` falls back to English when a translation is missing, so you only
    translate the fields where it actually matters.
    """

    def get(self, lang: Lang) -> str:
        if isinstance(self.root, str):
            return self.root
        return self.root.get(lang) or self.root.get("en") or next(iter(self.root.values()), "")

    def has(self, lang: Lang) -> bool:
        """True if this string carries an explicit translation for ``lang``."""
        return isinstance(self.root, dict) and lang in self.root

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return self.get("en")


def _as_str(value: object) -> object:
    """Stop YAML from turning ``2023`` into an int or ``2023-01-15`` into a date."""
    if value is None or isinstance(value, str):
        return value
    return str(value)


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


class Link(Base):
    id: str
    label: str
    url: str
    # Free-text key the designed template maps to a fontawesome glyph.
    icon: str = "link"


class Personal(Base):
    full_name: str
    headline: Localized
    email: str
    phone: str | None = None
    location: Localized | None = None
    # Path relative to the repo root. Designed variant only.
    photo: str | None = None
    links: list[Link] = Field(default_factory=list)


class Bullet(Base):
    id: str
    text: Localized


class Experience(Base):
    id: str
    company: str
    title: Localized
    location: Localized | None = None
    start: str
    end: str | None = None  # None means "present"
    tech: list[str] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)

    _str_dates = field_validator("start", "end", mode="before")(_as_str)


class Education(Base):
    id: str
    institution: str
    degree: Localized
    field: Localized | None = None
    location: Localized | None = None
    start: str
    end: str | None = None
    bullets: list[Bullet] = Field(default_factory=list)

    _str_dates = field_validator("start", "end", mode="before")(_as_str)


class Certificate(Base):
    id: str
    name: Localized
    issuer: str
    date: str
    url: str | None = None
    credential_id: str | None = None

    _str_dates = field_validator("date", mode="before")(_as_str)


class Project(Base):
    id: str
    name: str
    url: str | None = None
    description: Localized | None = None
    tech: list[str] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)


class Skill(Base):
    id: str
    name: str
    category: str = "general"
    level: str | None = None


class SpokenLanguage(Base):
    id: str
    name: Localized
    level: Localized


class Profile(Base):
    personal: Personal
    summary: Localized
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certificates: list[Certificate] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    languages: list[SpokenLanguage] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Tailoring (the model's output)
# --------------------------------------------------------------------------


class Strict(BaseModel):
    """Base for models handed to the API as a structured-output schema.

    Structured outputs require ``additionalProperties: false`` and every
    property listed in ``required``, so these models take no defaults — the
    model must fill in every field, using an empty list where nothing applies.
    """

    model_config = ConfigDict(extra="forbid")


class TailoredBullet(Strict):
    source_id: str = Field(
        description="id of the profile bullet, or of its parent entry, that this line is drawn from."
    )
    text: str = Field(description="The bullet as it should appear on the CV, already in the target language.")


class TailoredEntry(Strict):
    source_id: str = Field(description="id of the profile experience/education/project entry.")
    bullets: list[TailoredBullet] = Field(description="Selected and rephrased bullets for this entry.")


class SkillGroup(Strict):
    name: str = Field(description="Group heading, in the target language, e.g. 'Languages' / 'Języki'.")
    skill_ids: list[str] = Field(description="ids of profile skills in this group, most relevant first.")


class Branding(Strict):
    company_name: str = Field(description="The hiring company's name as it appears in the posting.")
    accent_hex: str = Field(
        description=(
            "The company's primary brand colour as #RRGGBB. Only give a colour you actually "
            "associate with this company; otherwise set confidence to 'low'."
        )
    )
    confidence: Literal["high", "low"] = Field(
        description="'high' only if you genuinely recognise this company's brand colour."
    )
    rationale: str = Field(description="One short sentence on where the colour came from.")

    @field_validator("accent_hex")
    @classmethod
    def _valid_hex(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("#"):
            v = "#" + v
        body = v[1:]
        if len(body) != 6 or any(c not in "0123456789abcdefABCDEF" for c in body):
            raise ValueError(f"accent_hex must be #RRGGBB, got {v!r}")
        return "#" + body.upper()


class TailoredCV(Strict):
    language: Lang = Field(description="Language this tailoring is written in.")
    headline: str = Field(description="Short professional title under the name, aimed at this role.")
    summary: str = Field(description="2-4 sentence profile summary aimed at this role.")
    branding: Branding
    experience: list[TailoredEntry] = Field(description="Relevant roles, most relevant first.")
    education: list[TailoredEntry]
    certificate_ids: list[str] = Field(description="ids of relevant profile certificates, most relevant first.")
    projects: list[TailoredEntry]
    skill_groups: list[SkillGroup]
    match_notes: str = Field(
        description="For the candidate's eyes only: why you chose this emphasis, and any gap versus the posting. Never rendered on the CV."
    )
