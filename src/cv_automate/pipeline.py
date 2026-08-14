"""Profile + tailoring -> PDF on disk.

The one place that knows the order of operations, so the CLI and the tests drive
the same path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .color import AccentDecision
from .compile import compile_pdf
from .models import Lang, Profile, TailoredCV
from .profile import build_index, validate_tailoring
from .render import build_document, make_env, render

VARIANTS = ("ats", "designed")


@dataclass
class Built:
    lang: Lang
    variant: str
    pdf: Path
    tex: Path
    warnings: list[str]


def build_cv(
    profile: Profile,
    tailored: TailoredCV,
    lang: Lang,
    variant: str,
    accent: AccentDecision,
    out_dir: Path,
    repo_root: Path | str = ".",
    keep_tex: bool = True,
) -> Built:
    """Validate, render and compile one CV.

    Validation runs first and unconditionally: a tailoring that references
    anything outside the profile never reaches a PDF.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")

    repo_root = Path(repo_root)
    index = build_index(profile)
    validate_tailoring(tailored, index)

    warnings: list[str] = []
    doc = build_document(profile, tailored, lang, accent.hex, index)

    # The ATS variant is deliberately monochrome — colour buys nothing a parser
    # can read, and risks something it cannot.
    resources: list[str] = []
    if variant == "designed" and doc.photo:
        if (repo_root / doc.photo).exists():
            resources.append(doc.photo)
        else:
            warnings.append(
                f"Photo not found at {repo_root / doc.photo}; rendering without it."
            )
            doc.photo = ""

    tex_source = render(doc, variant, make_env())

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"cv-{variant}.pdf"
    tex_path = out_dir / f"cv-{variant}.tex"
    if keep_tex:
        tex_path.write_text(tex_source, encoding="utf-8")

    result = compile_pdf(tex_source, pdf_path, resources=resources, repo_root=repo_root)
    warnings.extend(f"{variant}/{lang}: {w}" for w in result.warnings)
    return Built(lang=lang, variant=variant, pdf=pdf_path, tex=tex_path, warnings=warnings)
