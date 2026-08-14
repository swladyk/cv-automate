"""Command line entry point."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .color import AccentDecision, clamp_accent, resolve_accent
from .compile import LatexError
from .fixtures import DEFAULT_ACCENT, stub_tailoring
from .job_input import JobInputError, load_job
from .models import Lang, TailoredCV
from .pipeline import VARIANTS, build_cv
from .profile import (
    ProfileError,
    TailoringError,
    load_profile,
    unreferenced_ids,
)
from .tailor import Overflow, TailorError, tailor

app = typer.Typer(
    add_completion=False,
    help="Generate job-tailored LaTeX CVs from one master profile.",
    no_args_is_help=True,
)
console = Console()

DEFAULT_PROFILE = Path("data/profile.yaml")
EXAMPLE_PROFILE = Path("data/profile.example.yaml")
DEFAULT_OUT = Path("out")
TAILORING_FILE = "tailoring.json"
SCHEMA_VERSION = 1


def _die(message: str) -> None:
    console.print(f"[bold red]Error[/] {message}")
    raise typer.Exit(code=1)


def _load(profile_path: Path):
    try:
        return load_profile(profile_path)
    except ProfileError as exc:
        _die(str(exc))


def _write_tailoring(
    path: Path,
    tailoring: TailoredCV,
    accent: AccentDecision,
    lang: Lang,
    job_path: Optional[Path],
    model: Optional[str],
    usage: Optional[dict],
) -> None:
    payload = {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lang": lang,
        "job": str(job_path) if job_path else None,
        "model": model,
        "usage": usage,
        # The resolved accent is stored, not just the proposal, so --reuse
        # reproduces the same PDF byte for byte.
        "accent": {
            "hex": accent.hex,
            "original": accent.original,
            "action": accent.action,
            "note": accent.note,
        },
        "tailoring": tailoring.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _accumulate_usage(usage: Optional[dict], result) -> dict:
    """Sum token usage across retries, so the reported cost is the real one."""
    usage = usage or {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "attempts": 0}
    usage["input_tokens"] += result.input_tokens
    usage["output_tokens"] += result.output_tokens
    usage["cache_read_input_tokens"] += result.cache_read_tokens
    usage["attempts"] = usage.get("attempts", 0) + 1
    return usage


def _report_overflow(over: list, language: str, max_pages: int, offline: bool) -> None:
    """Say plainly that the page limit was missed, and what to do about it."""
    detail = ", ".join(f"{b.variant} is {b.pages} pages" for b in over)
    console.print(
        f"[bold yellow]Over the page limit[/] ({language}): {detail}, limit is {max_pages}."
    )
    if offline:
        console.print(
            "[dim]  --stub selects everything and --reuse re-renders a saved selection, so "
            "neither trims. Run without them to have the length enforced.[/]"
        )
    else:
        console.print(
            "[dim]  The PDFs were still written — trim them by hand, raise the ceiling with "
            "--max-pages 2, or allow another attempt with --retries 2.[/]"
        )


def _read_tailoring(path: Path) -> tuple[TailoredCV, AccentDecision]:
    if not path.exists():
        _die(
            f"No cached tailoring at {path}. Run without --reuse once to create it."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    tailoring = TailoredCV.model_validate(payload["tailoring"])
    stored = payload.get("accent", {})
    accent = AccentDecision(
        hex=stored.get("hex", DEFAULT_ACCENT),
        original=stored.get("original", DEFAULT_ACCENT),
        action=stored.get("action", "kept"),
        note="",
    )
    return tailoring, accent


@app.command()
def init(
    profile_path: Path = typer.Option(DEFAULT_PROFILE, "--profile", help="Where to write the profile."),
) -> None:
    """Scaffold data/profile.yaml and .env from the shipped examples."""
    if profile_path.exists():
        console.print(f"[yellow]{profile_path} already exists; leaving it alone.[/]")
    else:
        if not EXAMPLE_PROFILE.exists():
            _die(f"Missing {EXAMPLE_PROFILE}; are you running from the repo root?")
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXAMPLE_PROFILE, profile_path)
        console.print(f"[green]Created[/] {profile_path} — edit it with your own history.")

    env_example, env = Path(".env.example"), Path(".env")
    if env_example.exists() and not env.exists():
        shutil.copy2(env_example, env)
        console.print(f"[green]Created[/] {env} — put your ANTHROPIC_API_KEY in it.")

    console.print("\nNext: edit your profile, then `cv gen jobs/<posting>.md`.")


@app.command()
def validate(
    profile_path: Path = typer.Option(DEFAULT_PROFILE, "--profile", help="Profile to check."),
) -> None:
    """Check the profile loads, ids are unique, and report what's in it."""
    profile = _load(profile_path)

    table = Table(title=f"{profile_path}", title_style="bold", show_edge=False)
    table.add_column("Section")
    table.add_column("Count", justify="right")
    for label, items in [
        ("Experience", profile.experience),
        ("Education", profile.education),
        ("Projects", profile.projects),
        ("Certificates", profile.certificates),
        ("Skills", profile.skills),
        ("Languages", profile.languages),
        ("Links", profile.personal.links),
    ]:
        table.add_row(label, str(len(items)))
    console.print(table)

    bullets = sum(len(e.bullets) for e in [*profile.experience, *profile.education, *profile.projects])
    console.print(f"\n{bullets} bullets available for the model to draw on.")

    orphans = unreferenced_ids(profile)
    if orphans:
        console.print(f"[yellow]Unreferenced ids (usually a typo):[/] {', '.join(orphans)}")

    missing_pl = [
        name
        for name, value in [("headline", profile.personal.headline), ("summary", profile.summary)]
        if not value.has("pl")
    ]
    if missing_pl:
        console.print(
            f"[dim]No Polish text for: {', '.join(missing_pl)}. "
            "Polish CVs will fall back to the English wording for these.[/]"
        )

    console.print("[green]Profile is valid.[/]")


@app.command()
def gen(
    job: Optional[Path] = typer.Argument(None, help="Saved job posting (.txt, .md or .pdf)."),
    lang: list[str] = typer.Option(["en", "pl"], "--lang", "-l", help="Languages to generate."),
    variant: list[str] = typer.Option(list(VARIANTS), "--variant", "-v", help="ats and/or designed."),
    accent: Optional[str] = typer.Option(None, "--accent", help="Force an accent colour, e.g. '#FF6B00'."),
    no_accent: bool = typer.Option(False, "--no-accent", help="Use your default accent, ignoring the company's."),
    default_accent: str = typer.Option(DEFAULT_ACCENT, "--default-accent", help="Your own accent colour."),
    max_pages: int = typer.Option(1, "--max-pages", min=1, help="Page limit per CV."),
    retries: int = typer.Option(1, "--retries", min=0, help="Extra attempts to fit the page limit."),
    reuse: bool = typer.Option(False, "--reuse", help="Re-render a cached tailoring. No API call."),
    stub: bool = typer.Option(False, "--stub", help="Select everything, rephrase nothing. No API call."),
    profile_path: Path = typer.Option(DEFAULT_PROFILE, "--profile", help="Profile to read."),
    out_dir: Path = typer.Option(DEFAULT_OUT, "--out", help="Output root."),
    model: Optional[str] = typer.Option(None, "--model", help="Override the Claude model."),
) -> None:
    """Tailor the profile to a job posting and compile the CVs."""
    langs: list[Lang] = []
    for value in lang:
        for part in value.split(","):
            part = part.strip()
            if part not in ("en", "pl"):
                _die(f"Unknown language {part!r}; expected 'en' or 'pl'.")
            if part not in langs:
                langs.append(part)  # type: ignore[arg-type]

    variants: list[str] = []
    for value in variant:
        for part in value.split(","):
            part = part.strip()
            if part not in VARIANTS:
                _die(f"Unknown variant {part!r}; expected one of {', '.join(VARIANTS)}.")
            if part not in variants:
                variants.append(part)

    if job is None and not stub:
        _die("Give a job posting, or pass --stub to render without one.")

    profile = _load(profile_path)

    posting = None
    if job is not None:
        try:
            posting = load_job(job)
        except JobInputError as exc:
            _die(str(exc))
    slug = posting.slug if posting else "stub"

    override = default_accent if no_accent else accent
    results = []

    offline = reuse or stub

    for language in langs:
        lang_dir = out_dir / slug / language
        lang_dir.mkdir(parents=True, exist_ok=True)
        cache_path = lang_dir / TAILORING_FILE
        usage: Optional[dict] = None
        used_model = None
        overflow: Optional[Overflow] = None
        attempt = 0

        # The model cannot see how long its output renders, so the only reliable
        # way to hold a page limit is to typeset it, measure, and ask again.
        while True:
            if reuse:
                tailoring, decision = _read_tailoring(cache_path)
                if override is not None:
                    decision = clamp_accent(override, default_accent)
                console.print(f"[dim]{language}: reusing {cache_path}[/]")
            elif stub:
                tailoring = stub_tailoring(profile, language)
                decision = clamp_accent(override or default_accent, default_accent)
            else:
                assert posting is not None
                label = "Tailoring" if attempt == 0 else f"Trimming to {max_pages} page(s)"
                try:
                    with console.status(f"{label} for {language}…"):
                        result = tailor(
                            profile,
                            posting,
                            language,
                            model=model or "claude-opus-5",
                            overflow=overflow,
                        )
                except TailorError as exc:
                    _die(str(exc))
                tailoring = result.tailoring
                used_model = model or "claude-opus-5"
                usage = _accumulate_usage(usage, result)
                decision = resolve_accent(
                    tailoring.branding.accent_hex,
                    tailoring.branding.confidence,
                    default_accent,
                    override,
                )
                console.print(
                    f"[dim]{language}: {result.input_tokens} in / {result.output_tokens} out"
                    f" ({result.cache_read_tokens} cached)[/]"
                )

            if decision.note and attempt == 0:
                console.print(f"[yellow]Accent[/] {decision.note}")

            built_variants = []
            for variant_name in variants:
                try:
                    built = build_cv(
                        profile, tailoring, language, variant_name, decision, lang_dir, repo_root=Path(".")
                    )
                except TailoringError as exc:
                    _die(str(exc))
                except LatexError as exc:
                    _die(str(exc))
                built_variants.append(built)

            longest = max(built_variants, key=lambda b: b.pages)
            if longest.pages <= max_pages or offline or attempt >= retries:
                break

            attempt += 1
            console.print(
                f"[yellow]{language}: {longest.variant} came to {longest.pages} pages "
                f"(limit {max_pages}) — asking for a shorter selection.[/]"
            )
            overflow = Overflow(pages=longest.pages, max_pages=max_pages, previous=tailoring)

        for built in built_variants:
            for warning in built.warnings:
                console.print(f"[yellow]Warning[/] {warning}")
            results.append((language, built.variant, built.pdf, built.pages))

        over = [b for b in built_variants if b.overflows(max_pages)]
        if over:
            _report_overflow(over, language, max_pages, offline)

        if not reuse:
            _write_tailoring(
                cache_path, tailoring, decision, language, job, used_model, usage
            )

        if tailoring.match_notes and not reuse:
            console.print(
                Panel(
                    tailoring.match_notes,
                    title=f"How this was tailored ({language})",
                    border_style="dim",
                )
            )

    table = Table(show_edge=False, title_style="bold")
    table.add_column("Language")
    table.add_column("Variant")
    table.add_column("Pages", justify="right")
    table.add_column("File")
    for language, variant_name, pdf, pages in results:
        over = pages > max_pages
        table.add_row(
            language,
            variant_name,
            f"[red]{pages}[/]" if over else str(pages),
            str(pdf),
        )
    console.print(table)
    console.print(
        "[dim]The ats variant is for upload forms; designed is for attaching or emailing.[/]"
    )


def main() -> None:  # pragma: no cover
    # Windows consoles default to cp1252, which cannot encode Polish output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
