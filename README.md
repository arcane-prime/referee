# Referee

Upload a research paper as a PDF. Referee parses it, checks every reference
against real academic databases, gives you a peer review grounded in real
sources, lets you edit the paper with plain-English commands, and exports it as
LaTeX.

Its one hard guarantee: **an AI edit can never silently change your citations.**

---

## Tech stack

**Backend** — Python 3.10+ · FastAPI · Pydantic v2 · uvicorn · httpx · lxml ·
citeproc-py · pytest · ruff

**Frontend** — Next.js 16 · React 19 · TypeScript · plain CSS

**External services**

| | Used for |
|---|---|
| GROBID | PDF → structured XML |
| OpenAlex | primary reference lookup (free, no key) |
| Semantic Scholar | fallback lookup and abstracts (free, key optional) |
| OpenAI `gpt-4.1-mini` | peer review and editing |

**Storage** — the filesystem. No database.

---

## Getting started

You need Python 3.10–3.14 and Node 18+. Docker is optional.

### 1 — Backend

```bash
cd backend
python -m venv .venv
```

**Activate the virtual environment.** Everything after this fails without it,
because the commands would run against your system Python instead:

```powershell
.venv\Scripts\Activate.ps1      # Windows PowerShell
```
```bash
source .venv/bin/activate       # macOS / Linux
```

Your prompt should now begin with `(.venv)`. Confirm it took:

```bash
python -c "import sys; print(sys.executable)"
# must print a path inside backend/.venv
```

Then install and run:

```bash
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
python -m uvicorn app.main:app --port 8000
```

### 2 — Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

### 3 — GROBID (optional)

```bash
docker run -d --name grobid -p 8070:8070 \
  -e JAVA_TOOL_OPTIONS="-XX:-UseContainerSupport -Xmx3g" \
  lfoppiano/grobid:0.8.0
```

Model loading takes 20–90 seconds after the container reports `Up`. Check with
`curl http://localhost:8070/api/isalive` — you want the literal `true`.

The `JAVA_TOOL_OPTIONS` is **not optional on WSL2**: without it the JVM tries to
read cgroup v2 memory limits, fails, and the container dies before GROBID
starts. Use the CRF image (~300 MB), not the deep-learning one (~10 GB, wants a
GPU).

Skip this entirely if you like — with no `GROBID_URL` set, the app uses a public
hosted instance.

### Configuration

Everything lives in `backend/.env`. Copy `backend/.env.example` — every value in
it matches the code's default, so an empty file and the example describe the
same system.

```bash
OPENAI_API_KEY=sk-...             # without it, review and edit use an offline stub
GROBID_URL=http://localhost:8070  # comment out to use the public instance
OPENALEX_MAILTO=you@example.com   # optional, but gives a much higher free quota
```

The app is built against the OpenAI API. Using another provider means one new
file — see `design/review.md`.

**It runs with no setup at all.** No `.env`, no API key, no Docker: the app
still starts and every screen works. Parsing falls back to public GROBID, and
the LLM falls back to an offline stub that returns empty but well-formed
results.

---

## Playing with it

Open **http://localhost:3000** and drop in a PDF. An arXiv paper works best —
its references actually resolve.

1. **Parsing starts on upload.** No button. The paper appears in under a second,
   and reference checking fills in underneath over the next 30–60 seconds.
2. **Left pane — your paper.** Citations render as chips carrying reference ids.
   A revision badge tracks edits. Scroll down for the reference list and export.
3. **Right pane, "Peer review"** — click *Get suggestions*. Each finding is
   anchored to an exact sentence and carries either a verified quote from the
   cited source's abstract, or a real linkable suggestion.
4. **Right pane, "Edit"** — try *"make the introduction shorter"*. You get a
   before/after diff per paragraph with a citation summary. Nothing is written
   until you tick the changes and hit apply.
5. **Export** — bottom of the left pane. Pick a citation style, download the
   `.tex`. It compiles with a single `pdflatex` run.

**Worth trying:** ask it to `remove all citations from the paper`. It will
refuse, and tell you exactly which citation markers each refused edit would have
dropped.

---

## Tests

```bash
cd backend
pytest                 # 160 tests, ~2 seconds
ruff check app tests
```

```bash
cd frontend
npm run typecheck
npm run build
```

No network, no API key and no Docker needed — the parser tests read a committed
file of real GROBID output, and the search and LLM layers sit behind interfaces
with offline stand-ins.

---

## Troubleshooting

**`uvicorn : The term 'uvicorn' is not recognized`**
The virtual environment is not active. Re-run the activate step, verify with
`python -c "import sys; print(sys.executable)"`, and prefer `python -m uvicorn`
over bare `uvicorn`.

**`pip install` starts compiling `lxml` or `pydantic-core`, then fails**
pip is running against a different Python than you think — almost always because
the venv is not active. Check `python --version` first. If your default Python
is genuinely unsupported, build the venv against a specific one:
`py -3.12 -m venv .venv`.

**GROBID keeps dying**
It needs ~2.4 GB of RAM and Docker may OOM-kill it. `docker start grobid` brings
it back. Only uploading a *new* PDF needs it — review, editing and export all
read from disk.

**Reference checking is slow or finds nothing**
OpenAlex has a daily quota. Setting `OPENALEX_MAILTO` raises it substantially.

---

## How it works

The design documents live in **[`design/`](design/)** — one per feature, plus
`connection.md` for how they fit together.

| Document | Covers |
|---|---|
| **[overview.md](design/overview.md)** | **start here** — the whole system in plain words, with a diagram |
| [connection.md](design/connection.md) | how the parts fit together, in more detail |
| [api.md](design/api.md) | every endpoint, its JSON, and the error catalogue |
| [extraction.md](design/extraction.md) | PDF → structured document |
| [verification.md](design/verification.md) | checking references against databases |
| [review.md](design/review.md) | LLM peer review |
| [edit.md](design/edit.md) | natural-language editing and citation safety |
| [export.md](design/export.md) | LaTeX and CSL |

Start with `overview.md`. If you only read one more after that, make it
`edit.md` — the citation-safety mechanism is the most interesting part.

---

## Known limitations

- Only numbered citation style is proven against real GROBID output.
- Reference parsing degrades on mathematics papers — 6 of 38 references failed
  on one test paper, each checked individually (two had the journal name glued
  into the title, one had no title, three are genuinely absent from the
  databases).
- Some review findings flag the authors' own contribution claims, because the
  model sees sentences in isolation.
- One edit command changes at most 8 paragraphs, and edits one block at a time —
  paragraphs are never merged or split.
- Export is LaTeX, not PDF. Structure survives the round trip; page layout and
  figures do not.
- References with no abstract are skipped rather than guessed at. That count is
  always reported.

**With more time:** retry failed lookups with the title truncated at the last
comma (measured to rescue ~2 references in 38); send paragraph context to the
review; support cross-block edits; commit an author-year parser fixture.

---

## A note on AI tools

Built with Claude Code, which the assessment allows. The architecture decisions
were argued through before any code was written, and `design/` records that
reasoning.

Verified rather than assumed: every stage was run against real papers with live
GROBID, OpenAlex, Semantic Scholar and OpenAI calls; the citation guarantee was
tested by diffing every block before and after each edit rather than trusting
the app's own summaries; each unresolved reference was checked by hand before
being called a database gap rather than a bug; and an independent browser-driven
test pass found three real defects that unit tests could not — all since fixed.

Numbers quoted in this README and in `design/` are measured, not estimated.
