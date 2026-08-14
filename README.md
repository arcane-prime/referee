# Referee

Upload a research paper as a PDF. Referee parses it, checks every reference
against real academic databases, reviews it with an LLM grounded in real
sources, lets you edit it with plain-English commands, and exports it as LaTeX.

Its one hard guarantee: **an AI edit can never silently change your citations.**

---

## Quick start

Three terminals. Roughly five minutes.

```bash
# 1 — backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # works as-is; see Configuration below
uvicorn app.main:app --port 8000

# 2 — frontend
cd frontend
npm install
npm run dev                       # http://localhost:3000

# 3 — parser (optional, see below)
docker run -d --name grobid -p 8070:8070 \
  -e JAVA_TOOL_OPTIONS="-XX:-UseContainerSupport -Xmx3g" \
  lfoppiano/grobid:0.8.0
```

Open **http://localhost:3000** and drop in a PDF. An arXiv paper works well
because its references actually resolve.

**It runs with no setup at all.** With no `.env`, no API key and no Docker, the
app still starts and every screen works: parsing falls back to a public GROBID
instance, and the LLM falls back to an offline stub that returns empty but
well-formed results. Add the pieces below to make it fully live.

---

## Requirements

| | Version used | Notes |
|---|---|---|
| Python | 3.10.8 | 3.10+ |
| Node | 24 | 18+ should work |
| Docker | any | only for local GROBID |

---

## Configuration

Everything lives in `backend/.env`. Copy `backend/.env.example` and edit — every
value there matches the code's default, so an empty file and the example
describe the same system.

The two that actually matter:

```bash
OPENAI_API_KEY=sk-...             # without it, review and edit use an offline stub
GROBID_URL=http://localhost:8070  # comment out to use the public instance
```

Worth setting:

```bash
OPENALEX_MAILTO=you@example.com   # opts into OpenAlex's polite pool
                                  # much higher quota, faster, and the courteous
                                  # way to use a free service at ~40 requests/paper
```

Other useful knobs, all with sensible defaults: `REVIEW_MODEL` (`gpt-4.1-mini`),
`REVIEW_CONCURRENCY` (12), `VERIFICATION_BUDGET_SECONDS` (75),
`SEMANTIC_SCHOLAR_API_KEY` (optional, free).

---

## GROBID — the part most likely to cost you an afternoon

GROBID does the PDF-to-XML parsing. You have two options.

### Option A — the public instance (zero setup)

Leave `GROBID_URL` commented out. It defaults to
`https://kermitt2-grobid.hf.space`. Shared and rate limited, but fine for a
first look.

### Option B — local Docker (recommended)

```bash
docker run -d --name grobid -p 8070:8070 \
  -e JAVA_TOOL_OPTIONS="-XX:-UseContainerSupport -Xmx3g" \
  lfoppiano/grobid:0.8.0
```

**The `JAVA_TOOL_OPTIONS` is not optional on WSL2.** Without it the container
starts and immediately dies with:

```
java.lang.NullPointerException: Cannot invoke "CgroupInfo.getMountPoint()"
  because "anyController" is null
```

The JVM tries to auto-detect container memory limits, cannot read the cgroup v2
layout the WSL2 kernel exposes, and exits before GROBID's own code runs.
`-XX:-UseContainerSupport` turns that introspection off; `-Xmx3g` then has to be
set explicitly because the JVM can no longer infer a heap size.

Use the CRF image (`0.8.0`, ~300 MB), not the deep-learning variant (~10 GB,
wants a GPU).

**Model loading takes 20–90 seconds** after the container reports `Up`. It
answers nothing during that window:

```bash
curl http://localhost:8070/api/isalive     # want the literal: true
```

GROBID needs about 2.4 GB of RAM. On a machine with 8 GB it may get OOM-killed
by Docker under memory pressure — `docker start grobid` brings it back, and only
uploading a *new* PDF needs it. Review, editing and export all read from disk.

---

## Using it

1. **Drop in a PDF.** Parsing starts immediately — no button. The manuscript
   appears in under a second, and reference checking fills in underneath over
   the next 30–60 seconds.
2. **Left pane** — your paper. Citations render as chips carrying reference ids,
   because that is what they are in storage. A revision badge tracks edits.
3. **Right pane, Peer review** — click *Get suggestions*. Each finding is
   anchored to an exact sentence and carries either a verified quote from the
   cited source's abstract or a real, linkable suggestion.
4. **Right pane, Edit** — type something like *"make the introduction shorter"*.
   You get a before/after diff per paragraph and a citation summary. Nothing is
   written until you tick the changes and apply. Any edit that would drop a
   citation is refused and says which markers were lost.
5. **Export** — bottom of the left pane. Pick a style, download the `.tex`. It
   compiles with one `pdflatex` run; the bibliography is embedded.

---

## Tests

```bash
cd backend
pytest                 # 160 tests, ~2 seconds
ruff check app tests
```

**No network, no API key and no Docker are needed.** The parser tests read a
committed file of real GROBID output; the search and LLM layers sit behind
`Protocol` interfaces with offline stand-ins.

The tests worth reading are in `tests/test_editing.py`. They pin the guarantee
the whole project rests on: that the model never sees a reference id, that a
dropped or invented citation marker is refused rather than repaired, and that a
tampered edit proposal is rejected on apply.

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

---

## How it works

Six backend modules, each with the same `api/` · `provider/` · `dto/` shape:

| Module | Does |
|---|---|
| `papers` | upload and store the PDF |
| `extraction` | PDF → structured document (GROBID → TEI → inline nodes) |
| `resolution` | references → real records (OpenAlex, Semantic Scholar) |
| `review` | LLM peer review, grounded in fetched abstracts |
| `editing` | natural-language commands → reviewable proposals |
| `export` | document → LaTeX with a citeproc-rendered bibliography |

**The design documents are in [`design/`](design/)** — one per feature plus
`connection.md` for how they fit together. Start with
[`design/connection.md`](design/connection.md) for the whole picture, or
[`design/edit.md`](design/edit.md) for the citation-safety mechanism, which is
the most interesting part.

The single idea everything follows from: a paragraph is not a string, it is a
list of inline nodes. A citation is an object pointing at a reference id, and
the characters `[12]` are never stored — they are produced at render time by the
UI, and at export time by citeproc from a real `.csl` stylesheet. So when the
LLM rewrites a paragraph, it is handed the prose with every citation replaced by
an opaque token it cannot read. It chooses *where* a citation sits; it can never
touch *what* it is.

### On disk

No database. One folder per paper:

```
backend/data/papers/<paper_id>/
    original.pdf      written once, never rewritten
    grobid.tei.xml    raw parser output
    library.json      every reference ever known — append-only
    rev_0.json        the extracted document
    rev_1.json        after the first approved edit
```

Revisions are append-only, so undo is reading a smaller number, and any revision
can be exported and diffed against another.

---

## Known limitations

Stated plainly rather than discovered.

**Parsing**
- Only numbered citation style is proven against real GROBID output.
  Author-year is detected but has no committed fixture.
- Footnotes are not captured.
- Reference parsing degrades on mathematics papers. On one test paper 6 of 38
  references failed to resolve: two had the journal name glued into the title by
  GROBID, one had no title at all, and three parsed perfectly but are genuinely
  absent from the databases (a 1967 Soviet journal, a 2026 paper not yet
  indexed, a poorly indexed 2009 one). Each was checked individually.

**Review**
- Some findings flag the authors' own contribution claims, because the model
  sees sentences in isolation. Fixing it properly means sending paragraph
  context.
- References with no abstract are skipped rather than guessed at. That count is
  reported in the summary.

**Editing**
- One command changes at most 8 paragraphs. The UI says so, and says when a
  command hit the limit.
- An operation edits one block; paragraphs are never merged or split.
- A citation is guaranteed to survive and stay in its block, but after a heavy
  rewrite it may not sit beside the exact clause a human would have chosen.

**Export**
- LaTeX, not PDF. The round trip preserves structure, not page layout — figures
  and two-column formatting are not reconstructed.
- In-text citation *numbering* comes from LaTeX; only the bibliography entry
  *formatting* comes from CSL. An author-year body would need `natbib`.

**Operational**
- OpenAlex has a daily quota. Without `OPENALEX_MAILTO` it is small, and
  exhausting it makes reference checking fall back to a slower Semantic Scholar
  path.
- There is no client-side rate limiter in front of the model.

### With more time

Persist the resolution query ladder (retrying a failed lookup with the title
truncated at the last comma would rescue ~2 references in 38 — measured, not
guessed); send paragraph context to the review so it stops flagging the authors'
own claims; support cross-block edits; and commit an author-year TEI fixture.

---

## A note on AI tools

This project was built with Claude Code, which the assessment explicitly allows.
The architecture decisions — citations as nodes rather than text, the
deflate/inflate mechanism, storing facts and deriving verdicts, the `Protocol`
seams — were argued through in conversation before any code was written, and
`design/` records that reasoning.

What was verified rather than assumed:

- **Every stage was run against real papers**, not fixtures alone: real GROBID
  output, live OpenAlex and Semantic Scholar lookups, real LLM calls.
- **The citation guarantee was tested by diffing every block** before and after
  each edit — chip counts, reference ids, grouping and order — rather than by
  trusting the app's own summary labels.
- **Failure modes were investigated individually.** The 6 unresolved references
  above were each checked against the database by hand before being written down
  as "genuinely absent" rather than "our bug".
- **An independent browser-driven test pass** was run against the finished app.
  It found three real defects that unit tests could not: the review reading a
  stale revision, the stats row not recomputing after an edit, and the
  8-paragraph cap being undisclosed. All three are fixed.

Claimed numbers in this README and in `design/` are measured, not estimated.
