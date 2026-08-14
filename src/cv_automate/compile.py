"""Run LaTeX and get a PDF out, or a readable error.

XeLaTeX specifically — not pdfLaTeX. The Polish path needs it (fontspec +
polyglossia), and the templates assume system fonts.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory


class LatexError(Exception):
    """The document did not compile. Message carries the relevant log lines."""


@dataclass
class CompileResult:
    pdf: Path
    pages: int = 0
    warnings: list[str] = field(default_factory=list)


def page_count(pdf: Path | str) -> int:
    """Pages in a PDF. Uses pypdf rather than pdfinfo, which may not be installed."""
    from pypdf import PdfReader

    return len(PdfReader(str(pdf)).pages)


# A badly overfull box means text is running off the edge of the page — the kind
# of bug you only catch by looking at the PDF. Small ones are normal and noisy,
# so only report the ones a reader would actually notice.
_OVERFULL = re.compile(r"^Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\)", re.MULTILINE)
OVERFULL_THRESHOLD_PT = 5.0


def overfull_warnings(log: str, threshold_pt: float = OVERFULL_THRESHOLD_PT) -> list[str]:
    """Report text that spills past the margin by more than ``threshold_pt``."""
    worst = sorted(
        (float(m.group(1)) for m in _OVERFULL.finditer(log)), reverse=True
    )
    return [
        f"Text runs {pt:.0f}pt past the margin (overfull hbox) — check the PDF."
        for pt in worst
        if pt > threshold_pt
    ]


# Lines LaTeX uses to report real problems, as opposed to the thousands of
# lines of font and package chatter around them.
_ERROR_LINE = re.compile(r"^(!|.*?\.(?:tex|sty|cls):\d+:)", re.MULTILINE)


def _useful_log_lines(log: str, limit: int = 40) -> str:
    """Pull the actual errors out of a LaTeX log, falling back to the tail."""
    hits: list[str] = []
    lines = log.splitlines()
    for i, line in enumerate(lines):
        if _ERROR_LINE.match(line):
            # An error plus the couple of lines that explain it.
            hits.extend(lines[i : i + 3])
    if hits:
        return "\n".join(hits[:limit])
    return "\n".join(lines[-limit:])


def compile_pdf(
    tex_source: str,
    out_pdf: Path,
    resources: list[str] | tuple[str, ...] = (),
    repo_root: Path | str = ".",
) -> CompileResult:
    """Compile ``tex_source`` to ``out_pdf``.

    ``resources`` are repo-root-relative paths (the photo, mainly) copied into
    the build directory at the same relative location, so the paths written into
    the LaTeX resolve without any TEXINPUTS games.
    """
    if shutil.which("latexmk") is None:
        raise LatexError(
            "latexmk not found on PATH. Install TeX Live (or MiKTeX) and make sure "
            "its bin directory is on PATH."
        )

    repo_root = Path(repo_root)
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="cv-automate-") as tmpdir:
        build = Path(tmpdir)

        for rel in resources:
            src = repo_root / rel
            if not src.exists():
                raise LatexError(f"Missing resource referenced by the CV: {src}")
            dst = build / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        tex_path = build / "cv.tex"
        tex_path.write_text(tex_source, encoding="utf-8")

        proc = subprocess.run(
            [
                "latexmk",
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "cv.tex",
            ],
            cwd=build,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        produced = build / "cv.pdf"
        log_path = build / "cv.log"
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else proc.stdout

        if proc.returncode != 0 or not produced.exists():
            raise LatexError(
                f"xelatex failed for {out_pdf.name}:\n\n{_useful_log_lines(log)}"
            )

        shutil.copy2(produced, out_pdf)
        warnings = overfull_warnings(log)

    return CompileResult(pdf=out_pdf, pages=page_count(out_pdf), warnings=warnings)


def pdf_to_text(pdf: Path | str) -> str:
    """Extract text the way an ATS parser would. Returns '' if pdftotext is absent."""
    if shutil.which("pdftotext") is None:
        return ""
    proc = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout if proc.returncode == 0 else ""
