# Extraction - turning a PDF into a structured document

**Module:** `backend/app/modules/extraction/`
**Route:** `POST /papers/{paper_id}/extract`

---

## What this feature does

A researcher uploads a PDF. This stage turns that PDF into a structured
document we can work with: the title, the authors, the sections, the
paragraphs, and - most importantly - every citation as a separate object
rather than as text.

The output is saved to disk as `rev_0.json`. Everything later in the app reads
that file.

---

## The one idea that shapes everything

**A paragraph is not a string. It is a list of small objects called inline
nodes.**

Take this sentence from a real paper:

> Transformers dominate NLP [12]. Recent work extends this to vision [13, 14].

Most tools would store that as one string. We store it as a list:

```
TextRun("Transformers dominate NLP ")
CiteNode(id="c_4", ref_ids=["ref_11"])
TextRun(". Recent work extends this to vision ")
CiteNode(id="c_5", ref_ids=["ref_12", "ref_13"])
TextRun(".")
```

Notice the characters `[12]` appear **nowhere**. The citation is an object
that points at reference entries. The `[12]` a reader sees is printed later,
at display time or export time.

Why this matters: in the editing stage an AI model rewrites paragraphs. If
citations were text, the model could delete one, change it, or invent one. As
objects, it never even sees them. This single decision is what makes "the AI
cannot break your citations" true by construction instead of by hoping.

### The four node types

| Node | Holds | Example |
|---|---|---|
| `TextRun` | ordinary prose | `"Transformers dominate NLP "` |
| `CiteNode` | a citation pointing at reference ids | `[12]` → `ref_12` |
| `XRefNode` | a pointer to a figure, table or equation | `"Table 2"` |
| `MathNode` | a formula | `\mathcal{L}(\theta)` |

Only `TextRun` content is ever editable prose. The other three are carried
around but never written by a model.

---

## The flow, step by step

```
PDF bytes
   ↓  GrobidProvider.parse()          send the PDF to GROBID
TEI XML                                a structured XML description of the paper
   ↓  TeiProvider.parse()             walk the XML
   ↓    ├─ InlineProvider.build()     turn mixed text+tags into inline nodes
   ↓    └─ ReferenceProvider.build_all()  read the bibliography
Document + list of RawReference
   ↓  StyleProvider.detect()          guess IEEE / APA / Nature
   ↓  save rev_0.json
ExtractionResultDto → the browser
```

---

## The files, and what each one does

### `provider/parser_backend.py`

A `Protocol` (an interface) with two methods: `parse()` and `is_alive()`.

Nothing else in the codebase knows GROBID exists - it only knows "something
that can parse a PDF". `ExtractionProvider` is typed against this interface, so
which parser is used is a wiring decision made in one place
(`api/dependencies.py`). Swapping GROBID for another parser means one new file
implementing these two methods.

**How the tests avoid needing GROBID is a separate thing**, and worth being
precise about. There is no fake parser. The extraction tests skip this layer
entirely: they read a committed file of real GROBID output
(`tests/fixtures/numbered.tei.xml`) and call `TeiProvider.parse()` directly, so
the step that would call GROBID is never reached.

That fixture is treated as **source, not as generated data**. It is what lets
the whole parser suite run in about a second with no Docker and no network, and
it is why any uploaded paper can be promoted into a test case by committing the
TEI it produced.

### `provider/grobid_provider.py`

Talks to the GROBID service over HTTP.

| Function | What it does |
|---|---|
| `parse()` | POSTs the PDF, gets TEI XML back |
| `is_alive()` | health check, used by `/parser/status` |
| `_looks_like_tei()` | checks the response is really XML |

`_looks_like_tei()` exists because the free public GROBID sometimes returns an
HTML error page with status 200. Without this check we would try to parse HTML
as TEI and produce a confusing failure much later.

`COORDINATE_ELEMENTS` asks GROBID for the position of each element on the page.
It must be a **list**, not a comma-joined string, or GROBID silently ignores it.

### `provider/tei_namespace.py`

Small helpers for reading TEI XML, which uses XML namespaces that make normal
lxml calls verbose. `find()`, `find_all()`, `text_of()`, `attr()`,
`local_name()`, `normalise_space()`. No logic, just readability.

### `provider/tei_provider.py`

Walks the TEI document and builds our `Document`.

| Function | What it does |
|---|---|
| `parse()` | the entry point; returns `(Document, [RawReference])` |
| `_title()`, `_authors()` | read the paper's metadata |
| `_front_matter()` | the abstract, kept as its own section |
| `_body_sections()` | walk each `<div>` into a `Section` |
| `_section()`, `_block()` | build sections and paragraphs |
| `_level()` | heading depth, from the section numbering |
| `_floats()` | figure and table captions, collected into one section |

### `provider/inline_provider.py` - the tricky one

This is the hardest file in the project. XML has "mixed content": text can sit
both *inside* a tag and *after* it. Getting this wrong drops words or leaves
stray brackets in the prose.

| Function | What it does |
|---|---|
| `build()` | main entry: a TEI paragraph → a list of inline nodes |
| `build_element()` | same, but treats the whole element as one node (used for display formulas) |
| `_flatten()` | walks the XML tree collecting text and tags in order |
| `_node_for()` | decides which node type a tag becomes |
| `_ref_node()` | builds a `CiteNode` or `XRefNode` from a `<ref>` tag |
| `_absorb_delimiters()` | pulls stray brackets into the citation |
| `_merge_adjacent_citations()` | joins `[12]` `,` `[13]` into one citation |
| `_coalesce()` | merges neighbouring `TextRun`s |

**The delimiter problem.** GROBID marks up `[12]` as just `12` inside a `<ref>`
tag, leaving the `[` and `]` outside as ordinary text. If we did nothing, the
prose would contain stray brackets like `"…dominate NLP [". "]"`. Worse, an AI
editing that prose could move or delete them.

`_absorb_delimiters()` pulls those brackets into the `CiteNode`, and
`_merge_adjacent_citations()` joins `[12, 13]` - which GROBID reports as two
separate refs with a comma between - back into one citation act.

These two run alternately until nothing changes, up to `MAX_NORMALISE_PASSES`
(4), because fixing one can expose the other.

The result is an invariant we test: **no TextRun produced by extraction
contains a citation marker.** On our test paper, 0 leaks out of 58 citations.

**Ranges are never expanded.** `[1-3]` stays as written. Expanding it to
`[1][2][3]` would invent citations the author did not write.

### `provider/reference_provider.py`

Reads the bibliography at the end of the paper.

| Function | What it does |
|---|---|
| `build_all()` | every `<biblStruct>` → a `RawReference` |
| `_raw_string()` | the entry exactly as printed, kept verbatim |
| `_to_csl()` | GROBID's fields → a `CSLItem` |
| `_authors()`, `_issued()`, `_pages()`, `_scope()`, `_idno()` | field-by-field mapping |
| `_csl_type()` | journal article vs book vs thesis |
| `_target_url()` | a URL if one was printed |

Two rules hold here. **`raw` is always kept**, even when parsing fails, so a
bad entry can still be shown to the user and searched as a plain string.
**Nothing is dropped** - the brief explicitly forbids silently losing a
citation.

### `provider/style_provider.py`

Guesses whether the paper uses numbered (`[12]`) or author-year
(`(Smith, 2019)`) citations, by sampling the markers.

`detect()` returns a style plus a confidence. If it saw fewer than
`MIN_SAMPLES` markers, or confidence is below `CONFIDENCE_THRESHOLD`, it
returns `"unknown"` rather than guessing. The user then picks at export time.

### `provider/id_minter.py`

Hands out ids like `c_4`, `x_2`, `m_1`. `mint()` returns the next id, `seq()`
returns the counter so it can be saved with the document. Ids created later by
an edit must never collide with these.

### `provider/extraction_provider.py`

The orchestrator. Holds no parsing logic of its own.

| Function | What it does |
|---|---|
| `extract()` | read PDF → parse → build → save `rev_0.json` → return the result |
| `load_document()` | read a saved document back without re-parsing |
| `load_references()` | re-derive references from the stored TEI |
| `_summarise()` | count sections, blocks, citations, unlinked markers |

`use_cached_tei=true` re-runs only the translation step against TEI already on
disk. Useful when changing the parsing code without calling GROBID again.

---

## Routes

### `POST /papers/{paper_id}/extract`

Parses the PDF and returns the document, the references, and a summary.

**It does not check references against any database.** That is a separate
request (see `verification.md`). Parsing takes under a second; checking
references takes half a minute or more. Making the user wait for both before
seeing anything was the wrong trade.

### `GET /parser/status`

Reports whether GROBID is reachable. Lives outside `/papers/...` so the word
`parser` can never be mistaken for a paper id.

---

## What we report honestly

| Reported | Meaning |
|---|---|
| `unlinked_citation_count` | a marker was found but matched no bibliography entry |
| `references.failed` | an entry whose title could not be parsed |
| `detected_style` = `unknown` | we were not confident, so we are not guessing |

All three are shown in the UI. A visible gap is worth more than a silently
dropped citation.

---

## Known limits

- Only numbered style is proven against real GROBID output; author-year is
  detected but not fixture-tested.
- Footnotes are not captured.
- Reference parsing degrades on mathematics papers. On one test paper 6 of 38
  references failed to resolve - two had the journal name glued into the title
  by GROBID, one had no title at all, and three parsed perfectly but are simply
  absent from the databases.
- Block-level page coordinates are sparse, though inline nodes all have them.
