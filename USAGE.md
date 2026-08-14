# Using cv-automate

The short version. See [README.md](README.md) for how it works and why.

## Setup (once)

```bash
pip install -e .
cv init
```

Then do three things:

1. **Put your API key somewhere outside the repo.** On Windows:
   `setx ANTHROPIC_API_KEY "sk-ant-..."`, then open a new terminal.
   Set a monthly spend cap in the Console while you're there — this tool costs
   cents per run, so a low cap will never get in your way.
2. **Fill in `data/profile.yaml`.** This is the evening well spent: it is the
   ceiling on every CV the tool will ever produce. Write bullets factually and
   in full — the model shortens and re-angles them per job, but it works only
   from what you wrote.
3. **Drop your photo at `data/assets/photo.jpg`.** Square-ish crops best; it's
   rendered in a circle. Used by the designed variant only.

Check it loads:

```bash
cv validate
```

## Per application

```bash
# 1. Save the posting. Copy the text from LinkedIn / Pracuj.pl into a file.
#    Pasting beats any scraper — most job boards block them.
#    The filename becomes the output folder name, so name it usefully.
notepad jobs/meridian-data-platform-engineer.md

# 2. Generate
cv gen jobs/meridian-data-platform-engineer.md
```

You get:

```
out/meridian-data-platform-engineer/
  en/  cv-ats.pdf  cv-designed.pdf  cv-ats.tex  cv-designed.tex  tailoring.json
  pl/  …
```

**Which file to send:**

- `cv-ats.pdf` → upload forms and large-company portals, where software reads
  your CV before a person does.
- `cv-designed.pdf` → email attachments, direct contacts, anything a human
  opens first.

Same facts in both. Send whichever fits the application.

**Read the "How this was tailored" panel it prints.** That's the model telling
you what it emphasised and — more usefully — where your profile falls short of
the posting. It's often worth more than the CV itself: it tells you whether to
apply and what to prepare for.

## Commands

| Command | What it does |
|---|---|
| `cv gen JOB` | Both languages, both variants |
| `cv gen JOB --lang pl` | Polish only |
| `cv gen JOB --variant ats` | ATS only |
| `cv gen JOB --accent '#FF6B00'` | Force the accent colour |
| `cv gen JOB --no-accent` | Your default colour, not the company's |
| `cv gen JOB --max-pages 2` | Allow two pages instead of one |
| `cv gen JOB --retries 2` | Extra attempts to fit the page limit |
| `cv gen JOB --reuse` | Re-render from the saved tailoring. **No API call.** |
| `cv gen JOB --stub` | Select everything, rephrase nothing. No API call. |
| `cv validate` | Check your profile loads |

Postings can be `.txt`, `.md` or `.pdf`.

`--reuse` is the one to remember: use it whenever you're adjusting a template or
retrying a compile, so you don't pay for a fresh tailoring every time you nudge
a margin.

## One page

CVs are capped at one page. The tool typesets, counts the pages, and if it's
over it tells the model what it produced and asks for a shorter selection — so
this usually just works without you doing anything.

If it's still over after the retry, you get the PDFs plus a warning. Then either
trim by hand, allow another attempt with `--retries 2`, or raise the ceiling
with `--max-pages 2`.

The output table shows page counts, in red when over:

```
 Language │ Variant  │ Pages │ File
 en       │ ats      │     1 │ out/…/cv-ats.pdf
 en       │ designed │     1 │ out/…/cv-designed.pdf
```

`--stub` and `--reuse` don't trim — the first selects everything by design, the
second re-renders a saved selection. Both will report the overflow and leave it.

## Worth knowing

**Read the designed PDF before you send it.** The tool guarantees nothing on
your CV is invented — every line traces back to an id in your profile, and it
refuses to render if that check fails. It cannot judge whether the *emphasis* is
honest. If it foregrounds two months of Kafka because the posting demands
streaming, that's technically sourced and still awkward in an interview.

**If it refuses,** it will name the ids it couldn't find and write nothing.
That means either the model invented something or the posting tried to inject
it. Re-run; if it repeats, the posting is worth a look.

**Costs** roughly $0.05–0.10 per language per job. The second language for the
same job is cheaper, because your profile is sent as a cached prefix.

**Keep ids stable.** Once an id is in `profile.yaml`, don't renumber it — old
`tailoring.json` files stop reproducing if you do.

**Polish and English** both work fully, including diacritics. Any text field in
the profile takes `{en: ..., pl: ...}`; anything without a Polish translation
falls back to the English wording, so translate only what matters.
