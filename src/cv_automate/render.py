"""Turn a profile + a tailoring into LaTeX source.

Two things here are load-bearing:

* **Jinja uses LaTeX-safe delimiters** (``\\VAR{}``, ``\\BLOCK{}``) so template
  syntax never collides with LaTeX's own braces.
* **Escaping is on by default.** Every value interpolated into a template is
  LaTeX-escaped unless the template explicitly asks for ``|raw``. The opposite
  default is how a stray ``&`` in a company name silently breaks a build.

Templates stay dumb: everything is localised and resolved into the view models
below before rendering, so a template never calls ``.get(lang)`` or looks
anything up by id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .models import (
    Certificate,
    Education,
    Experience,
    Lang,
    Localized,
    Profile,
    Project,
    TailoredCV,
)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

# --------------------------------------------------------------------------
# Escaping
# --------------------------------------------------------------------------

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(c) for c in _ESCAPES))


class Raw(str):
    """A string the template author has vouched for; ``finalize`` leaves it alone."""


def latex_escape(value: str) -> str:
    """Escape LaTeX's special characters in one pass.

    Single-pass matters: escaping ``\\`` first and then ``{`` would mangle the
    ``\\textbackslash{}`` we just introduced.
    """
    return _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group()], value)


def _finalize(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Raw):
        return str(value)
    if isinstance(value, str):
        return latex_escape(value)
    return value


def make_env(templates_dir: Path | str = TEMPLATES_DIR) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        # LaTeX-safe delimiters: nothing here collides with { } or %.
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        # No line_statement_prefix on purpose: "%%" is common in hand-written
        # LaTeX and would silently become a Jinja statement.
        line_comment_prefix="%#",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # we escape for LaTeX, not HTML, via finalize
        finalize=_finalize,
        undefined=StrictUndefined,  # a typo in a template should fail, not render blank
    )
    env.filters["raw"] = Raw
    env.globals["icon"] = icon
    return env


# fontawesome5 commands, keyed by the free-text `icon` field in profile links.
_ICONS = {
    "github": r"\faGithub",
    "gitlab": r"\faGitlab",
    "linkedin": r"\faLinkedin",
    "globe": r"\faGlobe",
    "website": r"\faGlobe",
    "mail": r"\faEnvelope",
    "email": r"\faEnvelope",
    "phone": r"\faPhone",
    "stackoverflow": r"\faStackOverflow",
    "medium": r"\faMedium",
    "orcid": r"\faOrcid",
    "twitter": r"\faTwitter",
    "kaggle": r"\faKaggle",
    "link": r"\faLink",
}


def icon(key: str) -> Raw:
    """Map a profile link's ``icon`` key to a fontawesome command."""
    return Raw(_ICONS.get(key.lower(), r"\faLink"))


# --------------------------------------------------------------------------
# Dates and section labels
# --------------------------------------------------------------------------

_MONTHS: dict[str, list[str]] = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "pl": ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"],
}

LABELS: dict[Lang, dict[str, str]] = {
    "en": {
        "summary": "Profile",
        "experience": "Experience",
        "education": "Education",
        "projects": "Projects",
        "certificates": "Certificates",
        "skills": "Skills",
        "languages": "Languages",
        "contact": "Contact",
        "present": "Present",
        "credential": "Credential",
    },
    "pl": {
        "summary": "Profil",
        "experience": "Doświadczenie",
        "education": "Wykształcenie",
        "projects": "Projekty",
        "certificates": "Certyfikaty",
        "skills": "Umiejętności",
        "languages": "Języki",
        "contact": "Kontakt",
        "present": "obecnie",
        "credential": "Nr",
    },
}


def format_date(value: str | None, lang: Lang) -> str:
    """``2023-03`` -> ``Mar 2023``; ``2023`` -> ``2023``; ``None`` -> present."""
    if not value:
        return LABELS[lang]["present"]
    parts = value.split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        month = int(parts[1])
        if 1 <= month <= 12:
            return f"{_MONTHS[lang][month - 1]} {parts[0]}"
    return parts[0]


def format_period(start: str, end: str | None, lang: Lang) -> str:
    return f"{format_date(start, lang)} – {format_date(end, lang)}"


def _loc(value: Localized | None, lang: Lang) -> str:
    return value.get(lang) if value is not None else ""


# --------------------------------------------------------------------------
# View models — what templates actually see
# --------------------------------------------------------------------------


@dataclass
class RenderedLink:
    label: str
    url: str
    icon: str


@dataclass
class RenderedEntry:
    """One experience / education / project block."""

    title: str  # job title, degree, or project name
    org: str  # employer, institution, or "" for projects
    location: str
    period: str  # "" for projects, which have no dates
    url: str
    tech: list[str]
    bullets: list[str]


@dataclass
class RenderedCert:
    name: str
    issuer: str
    date: str
    url: str
    credential_id: str


@dataclass
class RenderedGroup:
    name: str
    items: list[str]


@dataclass
class CVDocument:
    lang: Lang
    labels: dict[str, str]
    accent_hex: str
    full_name: str
    headline: str
    summary: str
    email: str
    phone: str
    location: str
    photo: str
    links: list[RenderedLink]
    experience: list[RenderedEntry]
    education: list[RenderedEntry]
    projects: list[RenderedEntry]
    certificates: list[RenderedCert]
    skill_groups: list[RenderedGroup]
    languages: list[RenderedGroup] = field(default_factory=list)


def _entry_from(item: Any, bullets: list[str], lang: Lang) -> RenderedEntry:
    """Build a render entry, taking every fact except the bullets from the profile.

    Only bullet prose comes from the model. Dates, employers, institutions and
    URLs are read straight off the profile so they cannot drift.
    """
    if isinstance(item, Experience):
        return RenderedEntry(
            title=_loc(item.title, lang),
            org=item.company,
            location=_loc(item.location, lang),
            period=format_period(item.start, item.end, lang),
            url="",
            tech=item.tech,
            bullets=bullets,
        )
    if isinstance(item, Education):
        degree = _loc(item.degree, lang)
        field_of = _loc(item.field, lang)
        return RenderedEntry(
            title=f"{degree} — {field_of}" if field_of else degree,
            org=item.institution,
            location=_loc(item.location, lang),
            period=format_period(item.start, item.end, lang),
            url="",
            tech=[],
            bullets=bullets,
        )
    if isinstance(item, Project):
        return RenderedEntry(
            title=item.name,
            org="",
            location="",
            period="",
            url=item.url or "",
            tech=item.tech,
            bullets=bullets or ([_loc(item.description, lang)] if item.description else []),
        )
    raise TypeError(f"{item!r} is not a renderable entry")


def build_document(
    profile: Profile,
    tailored: TailoredCV,
    lang: Lang,
    accent_hex: str,
    index: dict[str, Any],
) -> CVDocument:
    """Join the tailoring back onto the profile into something a template can print.

    Assumes ``validate_tailoring`` has already run, so every id resolves.
    """

    def entries(group: list[Any]) -> list[RenderedEntry]:
        out = []
        for tailored_entry in group:
            item = index[tailored_entry.source_id]
            out.append(
                _entry_from(item, [b.text for b in tailored_entry.bullets], lang)
            )
        return out

    certs = []
    for cert_id in tailored.certificate_ids:
        cert: Certificate = index[cert_id]
        certs.append(
            RenderedCert(
                name=_loc(cert.name, lang),
                issuer=cert.issuer,
                date=format_date(cert.date, lang),
                url=cert.url or "",
                credential_id=cert.credential_id or "",
            )
        )

    skill_groups = [
        RenderedGroup(name=g.name, items=[index[s].name for s in g.skill_ids])
        for g in tailored.skill_groups
        if g.skill_ids
    ]

    languages = [
        RenderedGroup(name=_loc(l.name, lang), items=[_loc(l.level, lang)])
        for l in profile.languages
    ]

    return CVDocument(
        lang=lang,
        labels=LABELS[lang],
        accent_hex=accent_hex.lstrip("#").upper(),
        full_name=profile.personal.full_name,
        headline=tailored.headline,
        summary=tailored.summary,
        email=profile.personal.email,
        phone=profile.personal.phone or "",
        location=_loc(profile.personal.location, lang),
        photo=profile.personal.photo or "",
        links=[
            RenderedLink(label=l.label, url=l.url, icon=l.icon)
            for l in profile.personal.links
        ],
        experience=entries(tailored.experience),
        education=entries(tailored.education),
        projects=entries(tailored.projects),
        certificates=certs,
        skill_groups=skill_groups,
        languages=languages,
    )


def render(doc: CVDocument, variant: str, env: Environment | None = None) -> str:
    """Render ``ats`` or ``designed`` to LaTeX source."""
    env = env or make_env()
    template = env.get_template(f"{variant}.tex.j2")
    return template.render(doc=doc)
