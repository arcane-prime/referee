# Connection — how the five stages work together

Read the other five documents for each feature on its own. This one is about
what happens between them: what calls what, what is written to disk, what
depends on what, and why the seams are where they are.

---

## The whole journey, in order

```
1. UPLOAD      POST /papers                      → paper_id, original.pdf saved
                    │
2. EXTRACT     POST /papers/{id}/extract         → Document, saved as rev_0.json
                    │                              (fires automatically on upload)
                    │
3. RESOLVE     POST /papers/{id}/resolve         → library.json
                    │                              (fires automatically after extract)
                    ├──────────────┬──────────────┐
                    ▼              ▼              ▼
4. REVIEW      POST /review   5. EDIT        6. EXPORT
               → findings     POST /edit/plan    GET /export.tex
                              → proposal          → .tex file
                                   │
                              POST /edit/apply
                              → rev_1.json
```

Steps 4, 5 and 6 are independent of each other. All three read from disk.

---

## What lives on disk

```
backend/data/
    papers/paper_9d9b776178a4/
        original.pdf      the upload — written once, never rewritten
        grobid.tei.xml    exactly what the parser returned
        library.json      every reference ever known — append-only
        rev_0.json        the extracted document
        rev_1.json        after the first approved edit
        rev_2.json        after the second
    cache/
        openalex/…        raw API responses, keyed by request
        semantic_scholar/…
        openai/…
```

There is **no database**. One folder per paper plus a shared response cache.

Three rules hold, and a lot of the design follows from them:

**`original.pdf` is never opened for writing after upload.** That is a product
promise, not tidiness: whatever the agent does, the researcher's own file is
still there to download.

**Revisions are append-only.** `rev_1` never overwrites `rev_0`. Undo is
"read a smaller number" rather than a reverse operation that has to be correct.
Export takes a revision number, so you can export the paper as it was before an
edit and diff the two files.

**`library.json` is append-only.** Once a work is in it, it stays — even if the
edit that introduced it was rejected. Otherwise a revision could end up pointing
at a reference that vanished.

---

## The two data models everything shares

Everything in `app/domain/` is pure Pydantic with **zero I/O**. No module owns
these; every module speaks them.

### `Document` — the paper

```
Document
  └── Section[]
        └── Block[]              paragraph | heading | abstract | caption | formula
              └── Inline[]       TextRun | CiteNode | XRefNode | MathNode
```

A `CiteNode` holds `ref_ids` pointing into the library. **The characters `[12]`
exist nowhere in stored data** — they are produced at render time, by the UI as
a chip and by citeproc at export.

`Document.ref_id_counts()` returns `{ref_id: times cited}`. Two different
features read the document through this one function:

- the **edit invariant**, to prove citations survived a change
- the **export**, to decide which references go in the bibliography

They therefore cannot disagree about what the paper cites.

### `Reference` and `Library` — the bibliography

```
RawReference     what extraction read off the page
      ↓
Reference        that entry after resolution tried to find it in a database
      ├── parsed        our own parse (a CSLItem)
      ├── resolution    status, score, matched record, abstract, reason
      └── provenance    parsed_from_pdf | fetched_from_api
```

`Reference.csl` is the single place downstream code reads bibliographic data
from. It returns the matched database record when resolved, and falls back to
our own parse otherwise — which is what decouples output quality from parser
quality.

`Reference.can_be_cited_by_the_agent` is the anti-fabrication gate, and it is a
property of the type rather than a rule in a prompt.

**Everything is CSL-JSON.** What is scraped from the PDF and what is fetched
from OpenAlex both become `CSLItem`, so the renderer never has to know where a
reference came from.

---

## What depends on what

```
        ┌─────────────────────────────────────────────┐
        │  domain/    document, library, csl, edit,   │  imports nothing
        │             review, geometry                │  but Pydantic
        └─────────────────────────────────────────────┘
                          ▲
        ┌─────────────────────────────────────────────┐
        │  core/      config, storage, library,       │  imports domain
        │             http_cache, exceptions           │
        └─────────────────────────────────────────────┘
                          ▲
     papers    extraction    resolution    review    editing    export
```

The dependency rules, and the one exception:

- **Nothing imports a feature module's provider from another feature module**,
  except where a stage genuinely operates on another's output.
- `resolution` calls `extraction.load_references()` — one narrow, read-only
  method. Resolution works on extraction's output by definition, and letting it
  parse TEI itself would create a second implementation of "what are this
  paper's references".
- `editing` and `export` borrow `RevisionProvider`. Both read the same
  `rev_N.json` files, and two readers with two ideas of the on-disk layout is
  how one exports a revision the other does not believe exists.
- `editing` and `export` borrow the LLM backend and library provider from
  `core` / `review` wiring, so there is **one** model client and **one**
  library reader per process.

**Composition happens in routes, not providers.** The extract route used to call
resolution inline; that made extraction depend on resolution, which already
depended on extraction. The cycle was real, not stylistic. Splitting them into
two requests removed it.

---

## The seams that make this testable

Four `Protocol` interfaces, so no module names a vendor.

| Protocol | Real implementation | How tests avoid it |
|---|---|---|
| `ParserBackend` | `GrobidProvider` | **bypassed** — tests start from a committed TEI fixture |
| `SearchBackend` | `OpenAlexProvider` + fallback | `StubSearch` returns hand-written `SourceRecord`s |
| `AbstractBackend` | `SemanticScholarProvider` | `StubAbstracts` |
| `LlmBackend` | `OpenAiProvider` | `StubLlmProvider`, also wired in when no API key is set |

Three of those four have a real stand-in class implementing the same shape. The
parser is the exception: there is no fake `GrobidProvider`. The extraction tests
read `tests/fixtures/numbered.tei.xml` — genuine GROBID output, committed and
treated as source — and call `TeiProvider` directly, so the parser layer is
never entered.

The protocol still earns its place: it is why swapping parsers would touch one
file. But the fixture, not a fake, is what makes those tests offline.

The result: **160 tests run in about two seconds with no network, no API key,
no Docker.** A real GROBID output file is committed as a fixture and treated as
source, not as generated data.

The same seams make provider swaps cheap. Replacing Cerebras with OpenAI was one
new file plus one function (`get_llm_backend()`), and nothing in the three
review passes, the planner or the writer moved. That function is the **only**
place in the codebase that names a model vendor.

---

## Why extract and resolve are two requests

They cost wildly different amounts of time:

```
extract  :     409 ms      one call to GROBID
resolve  :  35,575 ms      38 lookups against public APIs that rate limit
```

Combined, the user stared at a spinner for 36 seconds with a finished parse
sitting on the server. Split, the manuscript appears in under half a second and
the verification panel fills in underneath.

The frontend fires them in sequence automatically — there is no Extract button,
because there was never a decision behind it.

This also changes what failure means. `extract` failing means there is nothing
to show. `resolve` failing means one panel is unavailable and everything else
still works. The UI holds them as two separate states for that reason.

---

## How the three later stages use what came before

| Stage | Reads | Calls out to |
|---|---|---|
| **Review** | `rev_N.json` + `library.json` | the model only |
| **Edit** | `rev_N.json` + `library.json` | the model only |
| **Export** | `rev_N.json` + `library.json` | nothing at all |

None of them re-parses the PDF, and none re-resolves references.

That was not always true, and the bug is worth recording. The review route used
to call `resolve_all()` on every request. With a warm HTTP cache it looked free;
with a cold one it meant 38 database lookups before a single claim could be
judged. A review that should take 20 seconds took over four minutes, all of it
rebuilding an answer already on disk. Reading `library.json` instead fixed it:

```
before : 282s+ (timing out)
after  :  16.3s   (no discovery)
          42.6s   (full review)
```

---

## The one thread running through all of it

Citations are nodes, never text — and that single decision pays off five times:

| Stage | What it buys |
|---|---|
| **Extraction** | brackets never leak into editable prose; unlinked markers are countable |
| **Verification** | a citation is a stable id to attach a database record to |
| **Review** | findings anchor to a sentence, and cited works are looked up by id |
| **Edit** | the model literally cannot see a citation, so it cannot break one |
| **Export** | `\cite{ref_12}`, and the printed form comes from a `.csl` file |

The rule stated once, in `domain/document.py`, and enforced everywhere after:

> **The LLM writes `TextRun` content and nothing else.** Every other inline is
> selected, moved, or removed with the user's approval — never authored.

---

## Failure handling, as a whole

Each stage degrades rather than cascading:

| What breaks | What still works |
|---|---|
| GROBID is down | everything except parsing a *new* PDF |
| OpenAlex out of quota | parse is fine; Semantic Scholar fallback; agent cannot add citations, and says so |
| Both databases down | parse and uncited-claim review still work |
| No API key set | stub backend; every route answers, review returns empty, model reports as `"stub"` |
| Model rate limits | the affected pass reports it; the parse is untouched |

Every failure is reported in words a researcher can act on, and the error shape
is always `{code, detail}` — `code` to branch on, `detail` to display.

Time budgets bound the two places that depend on outside services:
`verification_budget_seconds` (75s) for resolution, `DISCOVERY_BUDGET_SECONDS`
(25s) for the review's search pass. Both convert a long silence into a bounded
wait and an honest message.

---

## The frontend, briefly

One screen after upload, split into two panes:

- **Left — the manuscript.** The parse at the current revision, with citation
  chips, a revision badge, the verification panel, the reference list, and the
  export control. Blocks a pending edit would touch are highlighted here.
- **Right — the agent.** Two tabs: *Peer review* and *Edit*.

The panes scroll independently, because the parse and the review are read
against each other and a single column costs a long scroll per comparison.

State ownership matches the backend's split: `parse` is a fact about the
extraction and never changes; `current` is the manuscript, which every approved
edit replaces. After an edit the page **re-reads** the document from
`GET /document` rather than patching its own copy, because the server has just
written a revision and rebuilding from anything else is how the two come to
disagree.

`InlineNodes.tsx` renders citation chips for **both** the manuscript and the
edit diff. One renderer, so a chip in the diff is drawn by the same code that
drew it in the paper — which is what makes a proposed change comparable to the
text it replaces.
