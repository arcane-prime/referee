# Session Handoff

Read `PROJECT_CONTEXT.md` first for the product brief. This file covers what has
been built, what was decided and why, and where to resume.

**To resume the Claude Code conversation:** `claude --resume` from
`C:\Users\Dinesh\Referee`. History is on disk and survives a restart.

---

## 1. Where we are

Stage 1 is complete and verified against a real paper.

| Stage | State |
|---|---|
| 1a. Upload | Done, verified through the browser |
| 1b. Extract | **Done, verified on a real arXiv PDF via local GROBID** |
| 2. Resolve | Not started |
| 3. Review | Not started |
| 4. Edit | Not started |
| 5. Export | Not started |

### Verified against arXiv 1706.03762 ("Attention Is All You Need")

| Check | Result |
|---|---|
| Citation markers leaked into editable prose | **0** |
| References parsed | **40** — exact match for this paper |
| Citations found / unlinked | 45 / 0 |
| Sections / blocks | 26 / 92 |
| Node types | 139 text, 45 cite, 14 xref, 12 math |
| Coordinates captured | 45/45 cite, 12/12 math, 14/14 xref |
| Style detected | `ieee` @ confidence 1.0 |
| Section depth | L1/L2/L3, matching the real structure |

`pytest` — **32 passed in 0.72s**, run against real GROBID output, no container
and no network needed.

Full browser flow confirmed: upload (201) then extract (200) with correct CORS
headers from `http://localhost:3000`. Extraction takes ~40s cold, ~11s warm.

---

## 2. Running GROBID — the part that will waste your afternoon

**The documented `docker run` command does not work on this machine.** It
starts and immediately exits with:

```
java.lang.NullPointerException: Cannot invoke "CgroupInfo.getMountPoint()"
  because "anyController" is null      at CgroupV2Subsystem.getInstance
```

The JDK inside the image tries to auto-detect container memory limits, cannot
read the cgroup v2 layout this WSL2 kernel exposes, and dies before GROBID's
own code runs. Nothing to do with GROBID or with the PDF.

### The command that works

```bash
docker run -d --name grobid -p 8070:8070 \
  -e JAVA_TOOL_OPTIONS="-XX:-UseContainerSupport -Xmx3g" \
  lfoppiano/grobid:0.8.0
```

`-XX:-UseContainerSupport` turns off the JVM's container introspection, which
is the thing that crashes. `-Xmx3g` is set explicitly because with container
support off the JVM can no longer infer a heap size, and the Docker engine here
only has **3.73 GiB** total.

Then wait — **model loading takes ~85 seconds** after the container reports
`Up`. It answers nothing during that window.

```bash
curl http://localhost:8070/api/isalive        # want the literal: true
```

Do not paste a trailing `# comment` into `cmd.exe`; `#` is not a comment
character there and curl will try to fetch it as a URL.

Use `lfoppiano/grobid:0.8.0` — the CRF image, ~300 MB. Not the deep-learning
variant (~10 GB, wants a GPU). GROBID also serves a browser UI at
`http://localhost:8070` for eyeballing TEI by hand.

**Do not run it with `--rm` while debugging.** A crashed container is removed
along with its logs, which is why the first two attempts left nothing to read.

### Pointing the app at it

`backend/.env` already contains:

```
GROBID_URL=http://localhost:8070
GROBID_TIMEOUT_SECONDS=180
```

---

## 3. Two bugs the real run exposed

Both were invisible against the hand-written fixture. Worth knowing about
because both were silent failures, not crashes.

### `teiCoordinates` was being ignored

Sent as one comma-joined string. GROBID reads that parameter as a **list**, and
a comma-joined value is accepted and then silently dropped — request succeeds,
output simply has no coordinates. First real run produced **2** coordinate
attributes across the whole document; after the fix, **329**.

It must be a repeated form field. In httpx that means a list *value* inside the
data dict, not a list as `data` itself — passing a list as `data` makes httpx
treat it as raw streaming content and fail at send time with a confusing
complaint about sync streams on an async client.

### Display formulas were being flattened into prose

`<formula>` is a block-level sibling of `<p>` inside a div, not something nested
in a paragraph. The parser built blocks by walking the element as a *container*,
which flattened the equation into a `TextRun`. Result: **0 MathNodes** in a
paper with 12 equations, and every equation sitting in prose the LLM is allowed
to rewrite — exactly what `MathNode` exists to prevent.

Fixed with `InlineProvider.build_element`, which treats the element itself as
one node. Now 12/12.

### And one test that was wrong, not the code

The invariant test flagged all of `[]()` in prose and reported 24 failures
against the real paper. Every one was legitimate: `(x 1 , ..., x n )`,
`LayerNorm(x + Sublayer(x))`, `(multiplicative)`.

Square brackets essentially never occur in academic prose, so their presence
does prove a leak. Parentheses occur constantly, so an author-year leak has to
be matched on *pattern* — a capitalised name followed by a year — not on the
bracket character. The suite now has separate checks for each, plus
`test_ordinary_parentheses_in_prose_are_left_alone` guarding the opposite
mistake of a parser that strips every paren.

---

## 4. Known extraction artifacts

Real GROBID output, not parser bugs. Worth listing in the submission's
limitations section.

- **Title carries a copyright banner.** For this paper GROBID returns
  *"Provided proper attribution is provided, Google hereby grants permission…
  Attention Is All You Need"*. Its header model folded arXiv's licence block in.
- **`Google Brain` appears in the author list.** An affiliation leaked into
  `analytic/author`.
- **Two junk sections** named `Input-Input Layer5`, from the attention
  visualisation figures in the appendix.
- **`Label Smoothing` is promoted to L1** when the paper has it under 5.4.

None affect citations, references, or the core invariant. A header-cleanup pass
would be a reasonable small improvement.

---

## 5. Resume here

1. **Second fixture, author-year style.** Only numbered style has been proven
   on real output. The brief requires handling more than one citation style, so
   run an APA/ACL paper (e.g. BERT, arXiv 1810.04805) through and commit its TEI
   as `tests/fixtures/author_year.tei.xml`, then parametrise the document tests
   over both.
2. **Stage 2, Resolve.** New module `modules/resolve/` with the same
   `api`/`provider`/`dto` shape. OpenAlex only (it carries Crossref metadata and
   has direct DOI lookup, so a second client buys little). Needs a keyed disk
   cache from day one — the same paper gets parsed dozens of times in
   development, and unkeyed public APIs throttle hard.
3. **`GET /papers/{id}`** so a stored parse can be read back without re-running
   extraction.
4. **`docker-compose.yml`** — must include the `JAVA_TOOL_OPTIONS` workaround
   above, or a fresh clone will hit the same crash.
5. Header cleanup for the artifacts in section 4.

---

## 6. Decisions made, and why

Argued through in session. Expensive to change later.

### Citations are nodes, never text

The load-bearing decision. A paragraph is not a string; it is a list of inline
nodes. The characters `[12]` exist nowhere in stored data and are produced only
at render time.

The mental model is a Slack `@mention`: you never store the string `@dinesh`,
you store `{type: "mention", user_id: 42}`, and it renders at display time.

This turns "the AI must not break citations" from a prompt instruction into a
countable property. `Document.ref_id_counts()` returns `{ref_id: occurrences}`,
and stage 4 compares that dict before and after a proposed edit.

### Four inline node types, not two

```
TextRun    prose - the only thing the LLM may write
CiteNode   points out of the paper, at the bibliography
XRefNode   points inside the paper - "Figure 3", "Table 2"
MathNode   an inline or display equation, held opaquely
```

The rule: **the LLM writes TextRun content and nothing else.** Everything else
is selected, moved, or removed with approval, never authored.

`XRefNode` guards against the AI rewriting "Figure 3" into "Figure 4".
`MathNode` is not primarily safety — it is needed for export, since equations
flattened to prose cannot be re-emitted as `$...$` in the `.tex`.

### Store facts, derive verdicts

Nothing evaluative is stored. `parse_quality` (`good`/`degraded`/`failed`) is a
**property** computed from which fields are present, not a column. Same for
`missing_fields`. So the parse report is a pure function over the model and
cannot disagree with the data it describes.

### Extraction never judges

The one exception is style detection, which genuinely guesses — so it returns a
confidence, falls back to `unknown` rather than to a plausible answer, and is
user-overridable. Everything else in extraction is transcription.

| Stage | Question | Answered by |
|---|---|---|
| 1 Extract | "What does the PDF literally say?" | plain code |
| Report | "How well did we parse it?" | plain code, derived |
| 2 Resolve | "Is this the same paper as this record?" | string similarity + threshold |
| 3 Review | "Does this source support this claim?" | **LLM** |
| 4 Edit | "How should this be rewritten?" | **LLM** |

### Ranges are never expanded

`[12]-[15]` produces `ref_ids = [ref_12, ref_15]`, **not** four ids. The
intermediate references are not stated in the markup, and inventing them would
be fabricating citations. `raw_marker` keeps the printed form so the gap stays
visible.

### Other settled calls

- **Sections flat with a `level`**, not a tree. Nothing downstream walks a tree.
- **Every block lives in a section.** Abstract and captions get synthetic
  sections (`s_front`, `s_floats`) so traversal has no special cases.
- **Captions in, footnotes out.** Captions cite work, and excluding them would
  make the citation count quietly wrong. Footnote markers are dropped rather
  than degraded to text, since their content is a superscript digit that would
  inject stray numbers into prose. Footnotes are a **stated limitation**.
- **Coordinates captured.** Only producible while reading the PDF, like source
  maps during a build. Nothing depends on them yet.
- **Reference ids are opaque.** `ref_12` comes from TEI `xml:id="b12"`, which is
  0-indexed emission order — so `ref_12` is printed as `[13]` in this paper. The
  number a reader sees comes from citeproc.
- **Extraction is an explicit call**, never a side effect of upload.
- **Raw TEI saved to disk**, so any paper can become a fixture and a bad parse
  can be diagnosed by reading what GROBID actually said.
- **`original.pdf` written once, never reopened for writing.** Product
  guarantee.

---

## 7. The one genuinely tricky piece of code

`backend/app/modules/extraction/provider/inline_provider.py`. Understand this
before changing anything in extraction.

TEI paragraphs are **mixed content**: a `<p>` holds text and child elements
interleaved. lxml exposes `.text` (before the first child) and `.tail` (after
each child), so the walk is: take `.text`, then for each child take the child as
a node plus its `.tail` as text.

GROBID is inconsistent about delimiters — it emits both:

```xml
networks <ref>[12]</ref> have      brackets INSIDE the ref
networks [<ref>12</ref>] have      brackets OUTSIDE the ref
```

The naive walk handles the first and strands `[` and `]` in TextRuns for the
second. `_absorb_delimiters` pulls matching pairs into `raw_marker`.

**Absorption and merging must alternate**, because neither alone suffices:

- `[<ref>12</ref>, <ref>13</ref>]` needs *merging* before its outer brackets sit
  adjacent to a single node.
- `[<ref>12</ref>], [<ref>13</ref>]` needs *absorption* before the separator
  between the nodes reduces to `", "`.

Running both to a fixed point (capped at 4 passes) handles either ordering.
Real output also contains `[35,2,5]` with no spaces, which the separator set
covers.

`collapse_whitespace` preserves whether a run *started or ended* with a space
while collapsing everything inside. A plain `" ".join(text.split())` drops the
boundary space and welds a word onto the following citation.

---

## 8. Layout

```
backend/
  app/
    main.py                     app factory, CORS, router registration
    core/
      config.py                 env-driven settings
      exceptions.py             domain errors + the single HTTP handler
      storage_provider.py       on-disk layout for one paper
      dependencies.py           shared provider wiring
    domain/                     shared models, only Pydantic, zero I/O
      geometry.py  csl.py  document.py  library.py
    modules/
      papers/                   upload            api/ provider/ dto/
      extraction/               PDF -> Document + RawReference[]
        api/extraction_routes.py    POST /papers/{id}/extract
                                    GET  /parser/status
        provider/
          parser_backend.py     Protocol: parse(pdf_bytes) -> TEI string
          grobid_provider.py    the only thing touching the network
          tei_namespace.py      namespace helpers - TEI lookups fail SILENTLY
                                without the prefix
          inline_provider.py    the mixed-content walk (see section 7)
          reference_provider.py biblStruct -> CSLItem
          tei_provider.py       TEI -> Document
          style_provider.py     the only inferring code in extraction
          extraction_provider.py orchestrator
        dto/extraction_dto.py
  tests/
    fixtures/numbered.tei.xml   REAL GROBID output, arXiv 1706.03762
    test_extraction.py          32 tests
  samples/attention.pdf         the source PDF
  requirements.txt  .env

frontend/                       Next.js 16, App Router, TypeScript
  app/page.tsx                  upload IS the homepage
  components/PdfUploader.tsx    upload only, never calls extract
  components/ExtractionPanel.tsx Extract button + parse view
  lib/api.ts
```

Module convention: every feature module has `api/` (routes + wiring),
`provider/` (logic), `dto/` (transport). **Providers import no web framework** —
they take data, return DTOs, raise domain errors. Only `core/exceptions.py`
knows how a domain failure becomes an HTTP status.

Shared domain models live in `app/domain/`, not in any module's `dto/`, because
extraction creates them, review reads them, edit rewrites them, export renders
them.

**No inline comments anywhere.** Every file has a `Notes` block at the bottom.
Keep this convention.

---

## 9. Running it

```bash
# GROBID first - see section 2 for the JAVA_TOOL_OPTIONS workaround
docker start grobid          # if the container already exists

# backend
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# tests - no Docker or network needed
cd backend && .venv/Scripts/python -m pytest tests/ -q

# frontend
cd frontend && npm run dev   # http://localhost:3000
```

Python is **3.10.8** while `PROJECT_CONTEXT.md` specifies 3.11+. Everything runs
fine on 3.10.

Frontend is **Next 16**, not 15 — npm flagged a CVE in 15.1.3 during install.
Next 16 rewrote `tsconfig.json` and `next-env.d.ts` itself and removed
`next lint`, so the script is `npm run typecheck`.

CORS allows 3000 and 3001 on both `localhost` and `127.0.0.1`, because Next
silently falls back to 3001 when 3000 is taken and the resulting CORS failure
points nowhere near the real cause.

When printing extraction output from a script on Windows, set
`PYTHONIOENCODING=utf-8` — the default cp1252 console cannot encode author
names like `Łukasz`.

---

## 10. Known gaps

- Only numbered style proven on real output. Author-year fixture still needed.
- Header artifacts listed in section 4.
- Footnotes not captured (deliberate; must appear in the limitations section).
- `GET /papers/{id}` does not exist — a parse can only be obtained by re-running
  extract.
- No `docker-compose.yml` yet, and it must carry the JVM workaround.
- Nothing persists to SQLite; storage is the filesystem only. Fine for the
  stated scope of one user on one machine.
- Block-level coordinates are sparse (21/92) even though inline nodes all have
  them. Not investigated; nothing depends on it.
