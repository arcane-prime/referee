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
| 2. Resolve | **Done** — OpenAlex primary, Semantic Scholar fallback, disk cache |
| 3. Review | **Done** — quote-before-grade, quotes verified in code |
| 4. Edit | **Done and verified end to end on a real paper** |
| 5. Export | Not started — the last code gap |

156 tests pass in under two seconds with no network, no API key and no Docker.
`ruff check` is clean, `tsc --noEmit` is clean, `next build` succeeds.

### Stage 4 verified live, on paper_1565d341a0ae

```
BEFORE  rev 0 | citations: 62
PLAN    1 change(s) ready for review. | patches: 1 | refused: 0
APPLY   Applied 1 change(s) as revision 1. Revision 0 is unchanged on disk.
AFTER   rev 1 | available: [0, 1]

CITATIONS IDENTICAL: True (62 -> 62)
s0.p0: 724 -> 414 chars
  cites before: [[ref_17,ref_33], [ref_15,ref_29], [ref_13], [ref_16,ref_12], [ref_36,ref_37]]
  cites after : [[ref_17,ref_33], [ref_15,ref_29], [ref_13], [ref_16,ref_12], [ref_36,ref_37]]
```

The paragraph lost 43% of its prose and all five citations survived with their
groupings intact. See `EDITING_PLAN.md` for the design this implements.

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

**The code is done. What is missing is what the brief actually asks you to
send.** Four of its five submission artifacts do not exist, and the one it says
it weighs most heavily is among them. Do not start a new feature.

Roughly seven hours of work, in this order:

1. **`README.md`** (~30 min). How to run it. If a grader cannot start the app,
   nothing else gets marked. Cover: Python venv, `pip install -r
   requirements.txt`, GROBID via Docker (section 2) or the public fallback,
   `OPENAI_API_KEY` optional, `npm install && npm run dev`, and that the tests
   need none of it.
2. **`docs/01-citation-parsing.md`** (~75 min). The brief asks for the pipeline
   steps, the intermediate representation, where CSL-JSON fits, and how styles
   and failures are handled. Weighted highest.
3. **`docs/02-agent.md`** (~75 min). How a command becomes actions, how
   operations are planned and run, how OpenAlex and Semantic Scholar are called,
   and how citations survive an edit. Weighted highest.
4. **AI-use note and limitations** (~30 min). Explicitly requested. Section 10
   below plus `EDITING_PLAN.md` §14 are most of the raw material.
5. **Export** (~90 min). The last code gap, and the one explicit brief
   requirement not met: render through `citeproc-py` from a real `.csl` file and
   emit LaTeX plus a bibliography. If the clock beats you, cut this and name it
   as a limitation — a missing export is survivable, a missing design doc is not.
6. **Screen recording** (~45 min). Goes last because it needs everything
   working. Upload, extract, review, edit, approve.

**The docs are largely already written.** Every source file ends with a notes
block explaining why it is the way it is. `document.py` on citations as nodes,
`inline_provider.py` on delimiter absorption, `matcher_provider.py` on
thresholds, `placeholder_provider.py` on deflate and inflate,
`invariant_provider.py` on the two independent guards. Writing the design docs
is mostly assembling and sequencing that, not thinking it out again.

Deferred deliberately, all fine to leave undone:

- Author-year fixture. Style detection works, but only numbered style is proven
  against real GROBID output.
- Client-side pacing. There is no token bucket in front of the model client.
  Not currently a problem on OpenAI, but it is the thing that would need adding
  if a provider with a tight per-minute limit were used again.
- Resolution query ladder. Retrying a failed lookup with the title truncated at
  the last comma would rescue roughly two references in thirty-eight. Measured,
  not guessed — see the Ern and Guermond case.

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

Raw material for the limitations section of the submission.

**Deliverables**

- `README.md` and both `docs/` writeups do not exist. Highest priority.
- No screen recording yet.
- Export does not exist, so the CSL requirement is half met: CSL-JSON is the
  canonical model throughout, but nothing renders through citeproc. The note at
  the bottom of `domain/csl.py` claiming otherwise is aspirational until then.

**Parsing**

- Only numbered style proven on real output. Author-year fixture still needed.
- Header artifacts listed in section 4.
- Footnotes not captured, deliberately.
- Reference parsing degrades badly on mathematics papers. On the Green's
  function paper, 6 of 38 references failed to resolve: two had the journal name
  glued into the title by GROBID, one had no title at all, and three parsed
  perfectly but are genuinely absent from OpenAlex (a 1967 Soviet journal, a
  2026 paper not yet indexed, a poorly indexed 2009 one). Verified individually,
  not assumed.

**Runtime**

- GROBID is OOM-killed by Docker on this machine. 7.8 GB of system RAM, WSL2
  takes half, GROBID idles at 2.4 GB of that. `docker start grobid` brings it
  back in about 40 seconds. Commenting out `GROBID_URL` in `backend/.env` falls
  back to the public instance and frees the memory.
- A full review takes about two minutes on a 335-sentence paper with 51
  citations to check. Responses are cached on the exact request body, so a
  second run over an unchanged paper is instant, which is what makes a screen
  recording repeatable.
- Papers extracted before `library.json` existed have no library, so the agent
  may not add citations to them. It can still shorten and rewrite, and the UI
  says so.

**Structural, all deliberate**

- No `docker-compose.yml`, and it must carry the JVM workaround.
- Storage is the filesystem, no database. Correct for one user on one machine.
- Block-level coordinates are sparse (21/92) though inline nodes all have them.
  Never investigated; nothing depends on it.
- An edit operates on one block. No merging or splitting of paragraphs.
- A citation is guaranteed to survive and stay in its block, but after a heavy
  rewrite it may not sit beside the exact clause a human would have chosen.
