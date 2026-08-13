# Backend Codebase Guide

Every route, every provider, every function — what it does and why it exists.
Written to be read top to bottom the first time, then used as a lookup.

For the product brief see `PROJECT_CONTEXT.md`. For current status and setup
see `HANDOFF.md`.

---

## 1. What the app does

A researcher uploads a paper as a PDF. We turn it into a structured document
where **citations are data, not text**, check it against real academic
databases, and let the user edit it with an AI that cannot break the citations.

Right now stages 1a and 1b are built.

```
 1a UPLOAD    PDF bytes    →  stored on disk, given an id
 1b EXTRACT   stored PDF   →  Document + RawReference[]
 2  RESOLVE   references   →  matched against OpenAlex        (not built)
 3  REVIEW    document     →  findings from an LLM            (not built)
 4  EDIT      command      →  new revision, citations intact  (not built)
 5  EXPORT    a revision   →  .tex + bibliography             (not built)
```

---

## 2. The one idea everything is built around

**A paragraph is not a string. It is a list of nodes.**

Instead of storing this:

```
"Recurrent networks [12] are strong."
```

we store this:

```
[ TextRun("Recurrent networks ")
  CiteNode(ref_ids=["ref_12"])
  TextRun(" are strong.") ]
```

The characters `[12]` exist **nowhere** in our data. They are generated when
the document is displayed or exported.

If you have used Slack, you already know this pattern. Slack does not store the
text `@dinesh`; it stores `{type: "mention", user_id: 42}` and renders your name
at display time. A citation is a mention.

Two things fall out of this, and they are the entire reason for the design:

1. An AI rewriting a sentence **cannot delete a citation**, because the citation
   was never part of the text it was given.
2. Citations become **countable**. Two citations before an edit, two after. So
   "never break the citations" is a check that either passes or fails, not a
   polite instruction in a prompt.

---

## 3. How the code is organised

```
app/
  main.py        starts the app, plugs in the modules
  core/          shared infrastructure (settings, errors, disk storage)
  domain/        the data models everyone shares. No I/O, no framework.
  modules/       one folder per feature
    papers/      upload
    extraction/  PDF → structured document
```

Every feature module has the same three folders:

| Folder | Holds | Rule |
|---|---|---|
| `api/` | routes and wiring | knows about HTTP |
| `provider/` | the actual logic | **never imports FastAPI** |
| `dto/` | request/response shapes | plain data |

**The rule that matters:** providers take data, return data, and raise plain
Python errors. They know nothing about the web. That is why they can be tested
without starting a server, and why a route is usually about six lines long.

`domain/` sits outside `modules/` because those models belong to no single
feature. Extraction creates them, review reads them, edit rewrites them, export
renders them.

**No inline comments anywhere.** Each file ends with a `Notes` block explaining
the non-obvious decisions. Keep that convention.

---

## 4. The two request flows

### Uploading a PDF

```
Browser
  │  POST /papers   (multipart file)
  ▼
paper_routes.upload_paper          read the bytes, hand them over
  ▼
PaperProvider.create_from_upload   check it is really a PDF, make an id
  ▼
StorageProvider.save_original      write data/papers/<id>/original.pdf
  ▼
{ paper_id, filename, size_bytes, uploaded_at }
```

Upload does **not** parse anything. It stores a file and stops.

### Extracting the content

```
Browser
  │  POST /papers/{paper_id}/extract
  ▼
extraction_routes.extract_paper
  ▼
ExtractionProvider.extract                     the orchestrator
  ├─ StorageProvider.read_original             get the PDF back
  ├─ GrobidProvider.parse                      PDF → TEI XML   (only network call)
  ├─ StorageProvider.save_tei                  keep the raw XML
  ├─ TeiProvider.parse                         TEI → Document + references
  │    ├─ InlineProvider                       paragraphs → nodes
  │    └─ ReferenceProvider                    bibliography → CSL records
  ├─ StyleProvider.detect                      numbered or author-year?
  └─ StorageProvider.save_revision             write rev_0.json
  ▼
{ paper_id, document, references, summary }
```

---

## 5. What lands on disk

```
backend/data/papers/paper_9d9b776178a4/
    original.pdf      the upload, written once and never changed again
    grobid.tei.xml    exactly what GROBID returned
    rev_0.json        the extracted document
```

No database. One folder per paper.

- **`original.pdf` is never reopened for writing.** That is a promise to the
  user, not tidiness: their original file is always downloadable, untouched.
- **`grobid.tei.xml` is kept** so a bad parse can be diagnosed by reading what
  the parser actually said, and so any upload can become a test fixture.
- **`rev_0.json` is revision zero.** Later approved edits will write `rev_1`,
  `rev_2`. Nothing ever overwrites an earlier revision, so undo is just
  pointing at a smaller number.

**Known gap:** references are not yet saved to disk. They are returned in the
response but there is no `library.json`. Stage 2 needs one.

---

## 6. Routes

| Method | Path | What it does |
|---|---|---|
| `POST` | `/papers` | Upload a PDF. Returns `paper_id`. |
| `POST` | `/papers/{paper_id}/extract` | Parse a stored PDF into a document. |
| `GET` | `/parser/status` | Is GROBID reachable? |
| `GET` | `/health` | Is the API alive? |

Live docs while running: **http://localhost:8000/docs**

### `POST /papers`

Takes a multipart form with a field named `file`.

Returns **201** and `{paper_id, filename, size_bytes, uploaded_at}`.

Errors: **400** if it is not a PDF or the file is empty, **413** if over 50 MB,
**422** if the `file` field is missing entirely.

### `POST /papers/{paper_id}/extract`

Optional query parameter `use_cached_tei=true` re-runs the translation against
XML already on disk **without calling GROBID again**. This is the loop the
parser is developed in: change a parsing rule, re-run in a second, no network.

Returns **200** with the document, the references, and a summary.

Errors: **404** if no such paper, **502** if GROBID is unreachable, **422** if
GROBID answered but its output could not be turned into a document.

The split matters: 502 means *try again, nothing was half-saved*. 422 means
*this file is the problem, retrying will not help*.

### `GET /parser/status`

Returns `{parser: "grobid", alive: true|false}`. Exists because the most common
failure while developing is "GROBID isn't running", and you should be able to
find that out without uploading a PDF and waiting for a timeout to tell you.

---

## 7. `app/main.py`

| Function | What it does | Why |
|---|---|---|
| `create_app()` | Builds the FastAPI app: CORS, error handlers, routers, `/health`. | A factory, not module-level code, so tests can build an isolated app with their own settings. |

Adding a module later is one import and one `include_router` line here.

---

## 8. `app/core/` — shared infrastructure

### `config.py`

| Thing | What it does | Why |
|---|---|---|
| `Settings` | All configuration in one class, read from environment or `.env`. | Every external address and limit is declared in one place instead of scattered through the code. |
| `Settings.papers_dir` | `data_dir / "papers"` | The one place the papers folder is named. |
| `get_settings()` | Returns a single cached `Settings`. | Everyone sees the same values; no re-reading `.env` per request. |

Notable settings: `max_upload_bytes` (50 MB), `grobid_url`,
`grobid_timeout_seconds`, `cors_origins`.

`cors_origins` covers ports 3000 **and** 3001 because Next.js silently moves to
3001 when 3000 is taken, and the resulting browser error points nowhere near
the real cause.

### `exceptions.py`

Our own error types. Providers raise these; they never touch HTTP.

| Error | Status | Means |
|---|---|---|
| `RefereeError` | 500 | Base class for all of ours. |
| `InvalidUploadError` | 400 | Not a PDF, or empty. |
| `UploadTooLargeError` | 413 | Over the size limit. |
| `PaperNotFoundError` | 404 | No paper with that id. |
| `StorageError` | 500 | Disk read/write failed. |
| `ParserUnavailableError` | 502 | GROBID unreachable or misbehaving. |
| `ExtractionFailedError` | 422 | GROBID answered, but its output was unusable. |

| Function | What it does | Why |
|---|---|---|
| `register_exception_handlers(app)` | Turns any `RefereeError` into `{code, detail}` with the right status. | The single place that knows how a logic failure becomes an HTTP response. This is what keeps providers framework-free. |

`code` is stable and meant for the frontend to branch on. `detail` is for humans
and may change wording.

### `storage_provider.py`

Owns the folder layout. Nothing else in the codebase builds a path.

| Function | What it does | Why |
|---|---|---|
| `paper_dir(id)` | `data/papers/<id>` | One folder per paper. |
| `original_path(id)` | `.../original.pdf` | |
| `tei_path(id)` | `.../grobid.tei.xml` | |
| `revision_path(id, n)` | `.../rev_n.json` | Revisions are numbered files. |
| `exists(id)` | Is there a PDF for this id? | Cheap check before doing work. |
| `save_original(id, bytes)` | Writes the uploaded PDF. | Called **once**, at upload, forever. |
| `read_original(id)` | Reads it back. Raises `PaperNotFoundError` if missing. | Extraction needs the bytes again. |
| `save_tei(id, xml)` | Writes GROBID's raw output. | Debugging and test fixtures. |
| `read_tei(id)` | Reads it, or `None` if absent. | Powers `use_cached_tei` — re-parse with no network. |
| `save_revision(id, n, json)` | Writes `rev_n.json`. | Extraction writes revision 0; edits will write 1, 2, … |
| `read_revision(id, n)` | Reads it, or `None`. | For reading a parse back later. |
| `_write_bytes` / `_write_text` | Make parent folders, write, convert `OSError` into `StorageError`. | Every write goes through one place, so disk failures are reported consistently. |

Returning `None` for a missing TEI but **raising** for a missing PDF is
deliberate: no TEI simply means "not parsed yet", while no PDF means the id is
wrong.

### `dependencies.py`

| Function | What it does | Why |
|---|---|---|
| `get_storage_provider()` | Builds one shared `StorageProvider`. | Two modules need it. Building it twice would mean the folder layout is defined twice. |

---

## 9. `app/domain/` — the shared models

Imports nothing but Pydantic. No I/O, no framework. Every stage's input and
output type lives here, so the seams between stages are visible from the type
signatures alone.

### `geometry.py`

| Thing | What it does | Why |
|---|---|---|
| `BBox` | A rectangle on a page: `page, x, y, width, height`. | Where something physically sits in the PDF. |
| `BBox.parse_coords(str)` | Parses GROBID's `"page,x,y,w,h;page,x,y,w,h"` format. Skips anything malformed instead of raising. | Coordinates are a convenience. No parse should fail because one rectangle was unreadable. |

**Why capture these at all?** They can only be produced while reading the PDF —
like source maps during a build. They are what would later let the UI highlight
a citation inside the user's original file. Adding them afterwards would mean
re-parsing every paper.

### `csl.py` — the citation data format

**CSL-JSON is a standard format for describing one published work**, with zero
formatting in it. Thousands of journal stylesheets (`.csl` files) exist that
turn it into IEEE, APA, Nature, and so on.

The mental model is dates. You never store `"13/08/2026"`; you store a timestamp
and format it at display time, because the same instant prints differently in
different places. Citations are the same problem:

```
Same CSLItem →  IEEE:  [12] J. Cheng et al., "Long short-term memory-networks…", 2016.
             →  APA:   Cheng, J. (2016). Long short-term memory-networks…
```

| Thing | What it does | Why |
|---|---|---|
| `CSLName` | An author: `family` + `given`, or `literal`. | `literal` holds organisations and names we could not confidently split. We never guess at splitting a name. |
| `CSLName.surname` | Best available surname. | Used for scoring matches in stage 2. |
| `CSLDate` | A date as `date-parts`, e.g. `[[2016]]` or `[[2016, 6, 12]]`. | CSL's way of expressing partial dates in one field. |
| `CSLDate.year` | Pulls the year out. | The only part stage 2 scores on. |
| `CSLDate.from_year(y)` | Builds one from a year. | Convenience for the parser. |
| `CSLItem` | One published work: title, authors, journal, year, volume, pages, DOI. | **The one shape all citation data takes**, whether scraped from a PDF or fetched from OpenAlex. |
| `CSLItem.year` | Publication year, or `None`. | |
| `CSLItem.first_author_surname` | First author's surname. | Match scoring. |
| `CSLItem.to_csl_json()` | Converts to real CSL-JSON: hyphenated keys, no nulls, no empty lists. | The renderer requires the wire format exactly. An empty `"editor": []` is not the same as an absent one. |

**Why one canonical shape matters:** GROBID, OpenAlex, and Semantic Scholar all
speak different formats. If each stayed in its own shape, every consumer — the
matcher, the reviewer, the exporter, the UI — would have to know where a
reference came from and branch on it. Normalising at the boundary means nothing
downstream ever asks that question.

### `document.py` — the paper itself

**The most important file in the codebase.** Read its `Notes` block.

**The four node types.** A paragraph is a list of these:

| Node | Is | Why it is a node and not text |
|---|---|---|
| `TextRun` | Plain prose. | **The only thing the AI is allowed to write.** |
| `CiteNode` | A citation pointing *out* of the paper, at the bibliography. | So the AI cannot delete or invent one. |
| `XRefNode` | A pointer *inside* the paper — "Figure 3", "Table 2". | So the AI cannot rewrite "Figure 3" into "Figure 4". |
| `MathNode` | An inline equation, kept opaque. | So the AI cannot mangle an equation — and so we can put it back as `$…$` when exporting. |

That gives one rule covering everything:

> **The AI writes `TextRun` content and nothing else.** Everything else is
> selected, moved, or removed with the user's approval — never authored.

| Thing | What it does | Why |
|---|---|---|
| `CiteNode.ref_ids` | Which references this points at. Can be several. | `[12, 13]` is **one** citation attached to **one** claim, so it is one node. |
| `CiteNode.raw_marker` | The marker exactly as printed, e.g. `"[12, 13]"`. | Used to guess the citation style, and to show the user what was on the page. |
| `CiteNode.is_linked` | Did we find a matching reference? | Empty `ref_ids` means the marker was found but could not be linked. That is **recorded, never dropped** — a visible gap beats a silent loss. |
| `Block` | One paragraph, with a stable id like `s2.p3`. | The unit the AI edits and the diff compares. |
| `Block.cite_nodes` | Just the citations in this block. | |
| `Block.display_text` | The prose only, citations removed. | What gets diffed and what the AI is shown. Lossy on purpose. |
| `Section` | Title, `level`, and blocks. | |
| `Document` | One revision of the paper. | |
| `Document.blocks()` | Walks every block in order. | |
| `Document.block(id)` | Finds one block by id. | How the AI addresses a paragraph. |
| `Document.cite_nodes()` | Every citation in the paper. | |
| `Document.ref_id_counts()` | `{ref_id: how many times used}` | **This is the safety check.** Stage 4 compares this dict before and after an edit. If a count dropped, the edit is rejected. |

Details worth knowing:

- **Block ids are frozen.** `s2.p3` is assigned at parse time and never changes.
  A paragraph inserted later gets a fresh id rather than renumbering its
  neighbours, because the AI, the diff, and revision comparison all key on ids.
- **`seq`** is a counter saved with the document, used to mint ids for anything
  created after parsing. Saved rather than in-memory, so ids cannot collide
  after a restart.
- **Sections are flat with a `level`**, not nested. Nothing downstream walks a
  tree — the AI edits blocks and the diff compares blocks — so a tree would be
  structure we maintain and never use.
- **`style`** is the only guessed field in the whole document. Hence it carries
  a confidence and defaults to `unknown`.

### `library.py` — the bibliography

| Thing | What it does | Why |
|---|---|---|
| `RawReference` | One bibliography entry as extracted. | This is stage 2's **input**. |
| `.raw` | The entry verbatim, exactly as printed. | **Always populated.** An entry whose fields failed to parse is still shown to the user and still searchable as one query string. Dropping it is the failure the brief forbids. |
| `.parsed` | A `CSLItem`, or `None`. | Our best guess at the fields. |
| `.has_title` / `.has_authors` / `.has_year` | Field presence checks. | |
| `.missing_fields` | Which of the three are absent. | For honest reporting. |
| `.parse_quality` | `good` / `degraded` / `failed`. | See below. |
| `Library` | All references for one paper. | |
| `Library.get(id)` | Look one up. | |
| `Library.ids` | Set of all ids. | Stage 4 checks new citations against this. |

**`parse_quality` is a computed property, not a stored field.** This is a
deliberate pattern used throughout: **store facts, compute verdicts.** Whether a
reference parsed well is our *opinion*, fully determined by which fields came
back. Storing it would duplicate state that can drift from the data it
describes. Because everything evaluative is derived, the parse report is a pure
function over the model and needs no plumbing of its own.

- `failed` — no title. We have a string and nothing else. Still kept.
- `degraded` — a title, but missing authors or year.
- `good` — title, at least one author, and a year.

None of this says whether the reference is **real**. A perfectly parsed entry
can describe a paper that does not exist. That is stage 2's job.

**About reference ids:** `ref_12` comes from GROBID's `xml:id="b12"`, which is
zero-indexed emission order. So `ref_12` is the paper's **13th** reference, not
its `[12]`. Ids are opaque handles; the number a reader sees comes from the
renderer at display time.

---

## 10. `app/modules/papers/` — upload

### `provider/paper_provider.py`

| Function | What it does | Why |
|---|---|---|
| `create_from_upload(filename, content)` | Validate → mint id → save → return the DTO. | The whole upload rule set, in one testable place. |
| `_validate(filename, content)` | Rejects empty files, files over the limit, and anything not starting with `%PDF-`. | **Checks the magic bytes, not the filename or content-type.** Both of those are supplied by the client and are wrong often enough to matter, even when nobody is being hostile. |
| `_new_paper_id()` | `paper_` + 12 random hex characters. | Short, unique, safe as a folder name. |

This provider imports no web framework. It takes bytes, returns a DTO, raises
domain errors — which is exactly what lets it be tested without a server.

### `api/paper_routes.py`

| Function | What it does |
|---|---|
| `upload_paper(file, provider)` | Reads the multipart body, calls the provider, returns the DTO. |

Six lines. No `try/except`, no `HTTPException` — failures are domain errors
handled centrally.

### `api/dependencies.py`

| Function | What it does | Why |
|---|---|---|
| `get_paper_provider()` | Builds `PaperProvider` with shared storage and the size limit. | Wiring lives in `api/` so providers never construct their own collaborators. That is what lets a test hand one a temporary folder. |

### `dto/paper_dto.py`

`UploadedPaperDto` — `paper_id`, `filename`, `size_bytes`, `uploaded_at`.

There is no request DTO because the payload is a file, not JSON.

---

## 11. `app/modules/extraction/` — PDF to document

### `provider/parser_backend.py`

A `Protocol` (an interface): `parse(pdf_bytes, filename) -> str` and
`is_alive() -> bool`.

**Deliberately narrow: PDF in, raw XML string out.** A backend knows nothing
about our models, and the XML parser knows nothing about HTTP.

That single seam is why the test suite runs in under a second with no container
and no network: capture GROBID's output once, commit it, replay it forever. It
is also the honest answer to "why a Java container instead of parsing the PDF
ourselves" — parsing is a pluggable stage, GROBID is the production choice, and
anything that can return TEI satisfies this interface.

### `provider/grobid_provider.py`

The **only** file in extraction that touches the network.

| Function | What it does | Why |
|---|---|---|
| `parse(pdf_bytes, filename)` | POSTs the PDF to GROBID, returns TEI XML. Retries transport failures and busy responses. | |
| `is_alive()` | Checks GROBID's liveness endpoint. | |
| `_looks_like_tei(body)` | Is the response actually TEI? | See below. |

The request options and why each is set:

| Option | Why |
|---|---|
| `consolidateCitations=0` | Stops GROBID calling external services to enrich references. That lookup is **stage 2's job**, done deliberately with scoring we control — not as an invisible side effect of parsing. |
| `includeRawCitations=1` | **The most important flag.** Makes GROBID return the verbatim reference string next to its parsed fields, so an entry whose parsing failed is still recoverable. Without it, a failed parse is a lost reference. |
| `teiCoordinates=[…]` | Asks for element positions on the page. **Must be a list**, not a comma-joined string — GROBID accepts a joined string and silently ignores it, so the request succeeds with no coordinates at all. This exact bug cost a real debugging session: 2 coordinates in the whole document instead of 329. |

Three failure behaviours worth knowing:

- **A timeout is not retried.** The request already used the whole budget; a
  second attempt would double a wait the user is sitting through.
- **HTTP 204 means "parsed it, found nothing"** — in practice a scanned PDF with
  no text layer. Reported as such rather than as an empty success.
- **HTTP 200 is not proof of success.** Hosted GROBID instances sit behind
  platform wrappers that answer 200 with an HTML "starting up" page. Handing
  that to an XML parser produces a confusing error blaming the document instead
  of the service — so the body is checked for a TEI root first.

### `provider/tei_namespace.py`

Small helpers for reading TEI XML.

| Function | What it does | Why |
|---|---|---|
| `local_name(el)` | Tag name without the namespace. | Also guards against comments, whose tag is not a string. |
| `find(el, xpath)` | First match, or `None`. | |
| `find_all(el, xpath)` | All matches. | |
| `text_of(el)` | All text inside, whitespace collapsed. | PDF-derived XML is full of line breaks from the page layout. Those record where words fell on a page, not content. |
| `attr(el, name)` | An attribute, trimmed. | |
| `normalise_space(s)` | Collapses runs of whitespace. | |

**Why this file exists at all:** every TEI element is really named
`{http://www.tei-c.org/ns/1.0}p`, not `p`. A lookup that forgets the namespace
does not error — it **silently matches nothing**. That is the single most common
way a TEI parser appears to work while returning empty documents. Routing every
query through these helpers keeps the namespace in one place.

### `provider/id_minter.py`

| Function | What it does | Why |
|---|---|---|
| `mint(prefix)` | Returns `c_0001`, `m_0002`, … | Unique ids for nodes. |
| `seq` | The current count. | Saved on the `Document` so later edits mint ids that cannot collide with existing ones. |

One minter is threaded through an entire parse.

### `provider/inline_provider.py` — the tricky one

**Read this file's `Notes` block before changing anything here.**

Turns a TEI paragraph into a list of nodes. TEI paragraphs are *mixed content*:
text and elements interleaved. lxml exposes `.text` (before the first child) and
`.tail` (after each child), so the walk is: take `.text`, then for each child
take the child as a node plus its `.tail` as text.

| Function | What it does | Why |
|---|---|---|
| `tei_target_to_ref_ids(target)` | `"#b12"` → `["ref_12"]`. Handles several ids in one attribute. | Links a marker to bibliography entries. |
| `collapse_whitespace(text)` | Collapses inner whitespace **but preserves whether the run started or ended with a space**. | A plain `" ".join(split())` drops the boundary space and welds a word onto the next citation. |
| `build(element)` | The full pipeline: flatten, then absorb + merge to a fixed point, then tidy. | The main entry point, for paragraphs. |
| `build_element(element)` | Treats the element **itself** as one node. | For display equations, which are siblings of paragraphs, not nested inside them. Using `build` here flattened equations into prose — 0 MathNodes in a paper with 12. |
| `_flatten(element)` | Walks mixed content into a flat node list. | The core `.text` / `.tail` walk. |
| `_node_for(element)` | Decides what one child becomes. | `ref` → citation or cross-reference, `formula` → math, `lb` → a space, anything else → recurse. |
| `_ref_node(element)` | Builds a `CiteNode`, `XRefNode`, or nothing. | Footnote markers are **dropped**, because their content is a superscript digit that would otherwise inject stray numbers into prose. |
| `_absorb_delimiters(nodes)` | Pulls `[` `]` or `(` `)` off the surrounding text into the citation's `raw_marker`. | See below — this is the important one. |
| `_merge_adjacent_citations(nodes)` | Merges citations separated only by punctuation into one node. | `[12, 13]` is one citation act on one claim. |
| `_merge(group, markers)` | Combines a group into a single node, de-duplicating ids. | |
| `_coalesce(nodes)` | Joins adjacent text runs, drops empty ones, trims the ends. | Tidy-up after the passes above. |

**Why `_absorb_delimiters` exists.** GROBID is inconsistent about where it puts
the brackets:

```xml
networks <ref>[12]</ref> have      brackets INSIDE the tag
networks [<ref>12</ref>] have      brackets OUTSIDE the tag
```

The plain walk handles the first and leaves `[` and `]` stranded in the text for
the second. That breaks the one rule the whole product rests on — **prose the AI
may rewrite must contain no citation characters** — on the very first real paper.

**Why absorbing and merging must alternate.** Neither is enough alone:

- `[<ref>12</ref>, <ref>13</ref>]` needs **merging first**, so the outer brackets
  end up next to a single node.
- `[<ref>12</ref>], [<ref>13</ref>]` needs **absorbing first**, so the separator
  between the two nodes reduces to `", "` and they can then merge.

Running both repeatedly until nothing changes handles either order. The pass
cap stops a pathological input from looping.

**Ranges are never expanded.** `[12]-[15]` produces `[ref_12, ref_15]`, not four
ids. The middle references are not stated anywhere in the markup, and inventing
them would be **fabricating citations** — the one thing this product must never
do. `raw_marker` keeps the printed form so the gap stays visible.

### `provider/reference_provider.py`

Turns each bibliography entry into a `RawReference`.

| Function | What it does | Why |
|---|---|---|
| `build_all(root)` | Finds every `biblStruct` and builds a reference. | |
| `_build(entry, index)` | Assembles id, raw string, parsed fields, coordinates. | |
| `_ref_id(entry, index)` | `xml:id="b12"` → `ref_12`. Falls back to position. | Ids must exist even if GROBID omits one. |
| `_raw_string(entry)` | Reads the verbatim string; falls back to the entry's own text. | **`raw` is never allowed to be empty.** |
| `_to_csl(entry, id)` | Maps TEI fields into a `CSLItem`. | |
| `_csl_type(...)` | Guesses journal article / conference paper / book. | |
| `_authors(entry)` | Reads author names; falls back to organisation names. | |
| `_issued(entry)` | Finds a four-digit year. | Bibliographies write dates in wildly inconsistent ways, and the year is the only part stage 2 scores on. An unparseable date is kept as text rather than discarded. |
| `_scope(entry, unit)` | Volume or issue number. | |
| `_pages(entry)` | Page range, from text or `from`/`to` attributes. | |
| `_idno(entry, kind)` | DOI or URL. | |
| `_target_url(entry)` | A link, if there is one. | |

TEI marks titles by level: `a` is the article, `j` the journal, `m` the
monograph. Which is the work and which the container depends on which are
present — that is what the title logic works out. An entry with no article
title is treated as a book rather than an article with a missing title.

`parsed` is `None` only when there is nothing at all to record. That is
different from a badly parsed reference, which still gets a `CSLItem` holding
whatever was found.

### `provider/tei_provider.py`

Turns the whole TEI document into a `Document`. **Pure function, no I/O**, which
is why the parser can be tested against a committed file.

| Function | What it does | Why |
|---|---|---|
| `parse(tei_xml, paper_id, document_id)` | The whole translation. Returns document + references. | |
| `_root(tei_xml)` | Parses the XML in recovery mode. | Real GROBID output occasionally has a malformed span. Salvaging a large document beats rejecting the paper. |
| `_title(root)` | Paper title, falling back to the first heading. | A visible placeholder beats a crash. |
| `_authors(root)` | The paper's own authors. | Needed for the export title block. |
| `_front_matter(root, inlines)` | Builds a synthetic `s_front` section holding the abstract. | See below. |
| `_body_sections(root, inlines)` | Every `div` becomes a section. | |
| `_section(div, index, inlines)` | Title, level, and blocks. Skipped if it has no blocks. | Drops the layout artefacts GROBID emits for page furniture. |
| `_block(element, ...)` | Builds one block from a `p` or a `formula`. | Uses `build_element` for formulas so equations stay `MathNode`s. |
| `_level(head)` | Depth from the heading number: `3.1` → level 2. | Subsections are depth, not nesting. |
| `_floats(root, inlines)` | Builds a synthetic `s_floats` section holding figure and table captions. | See below. |

**Why synthetic sections.** Every block lives inside a section, so the abstract
and the captions get their own rather than becoming special fields on
`Document`. That keeps traversal uniform — anything walking the paper sees one
shape with no special cases — and it means **the citation count is
automatically correct**, because captions are walked alongside body paragraphs.

**Captions are in scope; footnotes are not.** Captions routinely cite work, so
excluding them would make the citation count quietly wrong. Footnotes being
excluded is a stated limitation, not an oversight.

### `provider/style_provider.py`

| Function | What it does | Why |
|---|---|---|
| `detect(cite_nodes)` | Looks at the markers and returns a style plus a confidence. | |

Mostly digits in brackets → `ieee`. Letters plus a plausible year → `apa`.
Fewer than three markers, or no clear majority → `unknown`.

**This is the only code in extraction that guesses.** Everything else writes
down what the page said. So it returns a confidence, and falls back to
`unknown` rather than to a plausible-looking answer. `unknown` is a genuinely
useful outcome: the user picks the style, and a paper that renders correctly
because the user chose beats one that renders wrongly because a heuristic was
confident.

### `provider/extraction_provider.py` — the orchestrator

| Function | What it does | Why |
|---|---|---|
| `extract(paper_id, use_cached_tei)` | Read PDF → get TEI → translate → detect style → save → summarise. | Owns the **sequence** and nothing else. Every step is independently testable, and this file contains no parsing logic. |
| `_summarise(document, references)` | Counts sections, blocks, citations, unlinked citations, and reference quality. | Computed on the way out, never stored, so it cannot disagree with the data. |

Two details:

- **`use_cached_tei`** re-runs the translation against XML already on disk. That
  is the loop the parser is actually developed in: change a rule, re-check in a
  second, no network, no container.
- **Style is applied by copying the document afterwards**, rather than letting
  the TEI parser know about style detection. The translator's job is
  transcription; the one guessed field is attached separately. That keeps the
  line between "what the page said" and "what we concluded" visible in the code.

### `api/extraction_routes.py`

| Function | What it does |
|---|---|
| `extract_paper(paper_id, use_cached_tei, provider)` | Awaits the orchestrator, returns the result. |
| `parser_status(parser)` | Reports whether GROBID is reachable. |

`parser/status` sits **outside** `/papers` on purpose: a literal path segment
inside a `{paper_id}` namespace is a collision waiting to happen — the moment a
`GET /papers/{paper_id}` exists, `"parser"` becomes a paper id that shadows it.

### `api/dependencies.py`

| Function | What it does | Why |
|---|---|---|
| `get_parser_backend()` | Builds the GROBID client from settings. | Typed as the **`ParserBackend` protocol**, not as `GrobidProvider`, so the choice of backend stays a wiring decision. Swapping the hosted instance for a local container is a settings change; swapping GROBID entirely is a change to this one function. |
| `get_extraction_provider()` | Assembles the orchestrator and its collaborators. | |

### `dto/extraction_dto.py`

| Thing | Holds |
|---|---|
| `ReferenceSummaryDto` | `total`, `good`, `degraded`, `failed`. |
| `ExtractionSummaryDto` | Section, block and citation counts, unlinked count, style. |
| `ExtractionResultDto` | `paper_id`, `extracted_at`, `parser`, `document`, `references`, `summary`. |

The response carries the **domain models directly** rather than a parallel set
of API shapes. `Document` and `RawReference` are already the contract every
later stage reads; mirroring them here would create two definitions of the same
thing, free to drift apart.

`unlinked_citation_count` is the honest one — markers found in the text that
could not be attached to any reference. Surfacing it is the point.

---

## 12. Tests

```bash
cd backend
.venv/Scripts/python -m pytest tests/ -v
```

They run against a committed TEI file — **no Docker, no network, under a
second.** That speed is the direct payoff of `GrobidProvider` returning a plain
string.

The most important test is the one asserting **no citation marker survives into
editable prose**. Everything in stages 3 and 4 assumes citations are nodes. If a
bracket ever leaks into a `TextRun`, the AI can delete a citation by rewriting a
sentence, and the counting check silently stops protecting anything.

Two subtleties in that test, learned from the real paper:

- **Square brackets** essentially never appear in academic prose, so finding one
  does prove a leak.
- **Parentheses appear constantly** — `(multiplicative)`, `LayerNorm(x)`. So an
  author-year leak has to be matched on *pattern* (a capitalised name followed
  by a year), not on the bracket character. There is also a test guarding the
  opposite mistake: a parser that strips every parenthesis.

To convince yourself the design holds, delete the `_absorb_delimiters` call from
`InlineProvider.build()` and re-run. The invariant test fails immediately,
showing brackets stranded in prose — exactly the bug that would let an AI
silently delete a citation.

---

## 13. Glossary

| Term | Means |
|---|---|
| **TEI** | The XML format GROBID outputs. An academic standard for marked-up documents. |
| **GROBID** | A Java service that turns a PDF into TEI. Runs in Docker on port 8070. |
| **CSL-JSON** | The standard data format for one published work, with no formatting in it. |
| **citeproc** | The renderer that combines CSL-JSON with a `.csl` stylesheet to produce `[12]` or `(Smith, 2019)`. |
| **In-text citation** | The `[12]` inside a sentence. In our model, a `CiteNode`. |
| **Reference** | The full entry at the end of the paper. In our model, a `RawReference`. |
| **Mixed content** | XML where text and elements interleave inside one element. |
| **`.text` / `.tail`** | lxml's way of exposing mixed content: text before the first child, and text after each child. |
| **DOI** | A permanent unique id for a paper, like `10.1038/nature14539`. |
| **Provider** | Our name for a class holding logic. Never imports a web framework. |
| **DTO** | A plain data shape for a request or response. |
