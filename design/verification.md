# Verification — checking references against real databases

**Module:** `backend/app/modules/resolution/`
**Route:** `POST /papers/{paper_id}/resolve`

---

## What this feature does

Extraction tells us what the paper's bibliography *says*. This stage finds out
what is *true*: does each reference name a real published work, and if so,
what is its DOI and abstract?

For each reference we search OpenAlex (and Semantic Scholar as backup), score
the results, and record one of three answers:

| Status | Meaning |
|---|---|
| `resolved` | we are confident this is the work, here is its DOI |
| `ambiguous` | plausible matches, none convincing enough — candidates kept |
| `unresolved` | nothing credible found, and we say so |

The result is saved to `library.json`. Two later stages depend on it: the
review needs abstracts to check claims against, and the editing agent may only
insert citations that point at entries here.

---

## Why this stage exists at all

A paper's PDF contains its bibliography, but **not the abstracts of the works
it cites**. Without going to a database, there is nothing to check a claim
against. This stage is what makes grounded review possible.

It also repairs the parser. If GROBID mangled a reference but the database
finds the right work, the output is correct anyway. That is what
`Reference.csl` does: it returns the matched record when resolved, and falls
back to our own parse otherwise. Output quality is decoupled from parser
quality.

---

## The flow

```
RawReference ("Vaswani et al. Attention is all you need. 2017")
   ↓
has a DOI?  ──yes──►  find_by_doi()          exact lookup, done
   │ no
   ↓
search()                                      title / author / year query
   ↓
list of SourceRecord candidates
   ↓  MatcherProvider.score()                 score each 0.0 – 1.0
   ↓  MatcherProvider.collapse_duplicates()   merge preprint + published
   ↓  MatcherProvider.decide()                resolved / ambiguous / unresolved
   ↓
abstract missing?  ──►  Semantic Scholar backfill
   ↓
Reference  →  library.json
```

---

## The files, and what each one does

### `provider/search_backend.py`

Two `Protocol` interfaces:

- `SearchBackend` — `find_by_doi()`, `search()`
- `AbstractBackend` — `find_abstract()`

Everything else talks to these, never to a specific API. This is what lets the
whole stage be tested offline with fake backends returning canned records.

### `provider/openalex_provider.py`

The main search client. OpenAlex is free and needs no key.

| Function | What it does |
|---|---|
| `find_by_doi()` | exact lookup by DOI |
| `search()` | title search, returns candidates |
| `_to_record()` | OpenAlex JSON → our `SourceRecord` |
| `_authors()`, `_venue()`, `_biblio()`, `_pages()` | field mapping |
| `_get()` | HTTP with retry and rate-limit handling |
| `_retry_after_seconds()` | reads the `retry-after` header |

Helper functions worth knowing:

**`reconstruct_abstract()`** — OpenAlex does not store abstracts as text. It
stores an *inverted index*: a map of word → positions. This rebuilds the
sentence.

**`looks_like_an_abstract()`** — sometimes the reconstructed text is not an
abstract at all but a citation string. This rejects text under
`MIN_ABSTRACT_CHARS` (180) or that looks citation-shaped (ends in a year, and
short). Without it, the review would grade claims against a bibliography entry
and produce nonsense.

**`filter_safe()`** — OpenAlex's filter syntax treats `,` `|` `:` `?` `*` and
others as operators. A title like *"Can active memory replace attention?"*
returns HTTP 400 unless those are stripped.

**`LONGEST_WORTHWHILE_WAIT_SECONDS`** — when the daily quota is exhausted,
OpenAlex replies with a `retry-after` measured in *hours*. Rather than hang, we
fail fast with a message stating the real wait ("resets in 19.8 hours").

### `provider/semantic_scholar_provider.py`

A second database, used two ways: as a **search fallback** when OpenAlex finds
nothing or is out of quota, and as an **abstract source** when OpenAlex has a
match but no abstract.

`find_by_doi()`, `search()`, `find_abstract()`, plus `_to_record()` and
`_clean()`.

### `provider/fallback_search_provider.py`

Wraps both clients into one `SearchBackend`. Tries OpenAlex first, falls back
to Semantic Scholar. The rest of the code never knows which one answered — it
only sees `search_api` reported as `"openalex+semantic_scholar"`.

### `provider/matcher_provider.py` — where the stage lives or dies

Pure scoring, no I/O. This decides whether a candidate really is the cited work.

**Scoring is weighted:**

| Signal | Weight | Function |
|---|---|---|
| title | 0.60 | `title_similarity()` |
| authors | 0.25 | `author_similarity()` |
| year | 0.15 | `year_similarity()` |

Year scoring is forgiving by design — `YEAR_SCORES` gives 1.0 for an exact
match, 0.85 for one year out, 0.5 for two. Preprints and published versions
often differ by a year and are the same work.

**Deciding, in `decide()`:**

| Rule | Value |
|---|---|
| `RESOLVED_THRESHOLD` | 0.82 — accept |
| `AMBIGUOUS_THRESHOLD` | 0.55 — below this, unresolved |
| `MIN_MARGIN_OVER_RUNNER_UP` | 0.04 — must beat second place by this much |

**`collapse_duplicates()`** exists because of a real bug. A paper published at
EMNLP and also on arXiv returned two candidates, both scoring 1.00. The margin
rule then declared it *ambiguous* — two perfect matches looked like confusion.
This function detects that two records describe the same work
(`describe_the_same_work()`), and keeps the better one
(`better_record_of()`, which prefers a published DOI over a preprint one via
`is_preprint_doi()`).

Every decision carries a `reason` string in plain English, for example
*"Best candidate scored 0.44, below the 0.55 threshold."* That sentence is
shown to the user.

### `provider/resolution_provider.py`

The orchestrator.

| Function | What it does |
|---|---|
| `resolve_all()` | run every reference, bounded concurrency |
| `resolve_one()` | one reference through the whole pipeline |
| `_find_records()` | DOI lookup first, then title search |
| `_backfill_abstract()` | ask Semantic Scholar when OpenAlex had none |

`resolution_concurrency` defaults to **3**. Forty sequential lookups is a long
wait; forty simultaneous ones is how a client earns a rate limit from a free
public service.

### `core/library_provider.py`

Not inside this module, because two modules need it. Resolution writes it,
editing and review read it.

| Function | What it does |
|---|---|
| `load()` | read `library.json`, or an empty library if absent |
| `merge()` | add new references by id, never overwrite existing ones |

**The library is append-only.** Once a work is in it, it stays. A reference
discovered while producing one revision is still citable from the next, and a
reference introduced by an edit the user rejected does not vanish and leave
some other revision pointing at nothing.

### `core/http_cache.py`

Caches raw API responses on disk, keyed by request.

- `request_key()` builds the key, and **excludes `mailto`** so changing your
  email does not invalidate the whole cache
- negative results are cached too, so a "not found" is not re-asked every run
- writes go to a temp file then get renamed, so a crash cannot leave a
  half-written cache entry

This is what makes development bearable against a 100k/day quota, and what
makes a screen recording repeatable.

---

## The route

### `POST /papers/{paper_id}/resolve`

1. Load the references from the stored TEI
2. Resolve them all, under a single time budget
   (`verification_budget_seconds`, default 75s)
3. Merge the results into `library.json`
4. Return the references plus a summary

**Why one budget for the whole step.** Without it, a paper with seventy
references discovers a database is throttling it seventy separate times, each
with its own backoff, and a request that should take under a minute grinds on
for many. The budget turns that into a bounded wait followed by an honest
failure. The parse is untouched either way.

A timeout is reported as `SearchUnavailableError` (HTTP 502) with a message
saying the parse is unaffected, because from the user's side their paper is
still on screen and only one panel failed.

---

## What we report honestly

The summary separates `resolved`, `ambiguous` and `unresolved` rather than
giving a single success rate, because the three mean different things to a
researcher. `with_abstract` is tracked separately, because that is the number
the review actually depends on: a reference can be confidently identified and
still have no abstract to check claims against.

Real numbers from one test paper (38 references):

```
resolved 31 | ambiguous 1 | unresolved 6 | with_abstract 26 | with_doi 31
```

The 6 failures were investigated individually rather than assumed: two had the
journal name glued into the title by GROBID, one had no title at all, and three
parsed perfectly but are genuinely absent from the databases (a 1967 Soviet
journal, a 2026 paper not yet indexed, and a poorly indexed 2009 one).
