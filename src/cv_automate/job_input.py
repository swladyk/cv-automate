"""Read a saved job posting off disk.

No parsing or structure extraction — the model reads the posting whole. This
only deals with getting bytes into a string and naming the output folder.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}
PDF_SUFFIXES = {".pdf"}


class JobInputError(Exception):
    """The posting could not be read."""


@dataclass
class JobPosting:
    slug: str
    path: Path
    text: str


# Letters with no NFKD decomposition, which ASCII-folding would otherwise drop
# entirely. Polish "ł" is the one that matters here: without this, "Żłobek"
# slugs to "zobek".
_TRANSLITERATE = str.maketrans(
    {
        "ł": "l", "Ł": "L",
        "ø": "o", "Ø": "O",
        "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D",
        "þ": "th", "Þ": "Th",
        "ß": "ss",
        "æ": "ae", "Æ": "Ae",
        "œ": "oe", "Œ": "Oe",
    }
)


def slugify(value: str) -> str:
    """Filename -> safe output-directory name."""
    value = value.translate(_TRANSLITERATE)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "job"


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise JobInputError("Reading PDF postings needs `pypdf`. pip install pypdf") from exc

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def load_job(path: str | Path) -> JobPosting:
    path = Path(path)
    if not path.exists():
        raise JobInputError(f"No job posting at {path}")

    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix in PDF_SUFFIXES:
        text = _read_pdf(path)
    else:
        supported = ", ".join(sorted(TEXT_SUFFIXES | PDF_SUFFIXES))
        raise JobInputError(f"Don't know how to read {suffix or 'a file with no extension'}. Supported: {supported}")

    text = text.strip()
    if len(text) < 50:
        raise JobInputError(
            f"{path} yielded only {len(text)} characters of text. "
            "If it's a scanned PDF, copy the posting into a .txt or .md file instead."
        )

    return JobPosting(slug=slugify(path.stem), path=path, text=text)
