# Review - peer review by an LLM, grounded in real sources

**Module:** `backend/app/modules/review/`
**Route:** `POST /papers/{paper_id}/review`

---

## What this feature does

Reads the paper and produces reviewer-style findings of three kinds:

| Finding | Meaning |
|---|---|
| `unsupported_claim` | a cited source does not actually support the claim attached to it |
| `missing_citation` | a claim carries no citation, and we found real works that could support it |
| `uncited_claim` | a claim carries no citation, and we could not search for sources |

Every finding is anchored to an exact sentence (block id, sentence index,
character span) and every one is **grounded**: it survives only if there is a
verified quote or a real linkable source behind it.

---

## The rule that makes this trustworthy

> **The model never asserts a verdict without showing its evidence, and the
> evidence is checked in code.**

For each cited claim we ask the model for two things together: a **quote from
the abstract** and a **grade**. Then, in ordinary Python, we check that the
quote actually appears in the abstract. If it does not, the grade is thrown
away and forced to `insufficient_evidence`.

This means anti-hallucination does not depend on the model being honest. A
model that invents a supporting sentence fails a string comparison.

The model also never sees the reference list - not the parsed entries, not the
unparsed ones. It only ever sees sentences, or one claim plus one abstract. It
cannot cite what it was never shown.

---

## The three passes

They are independent and separately switchable, and they need progressively
more of the outside world:

| Pass | Needs | Query flag |
|---|---|---|
| uncited claims | the document alone | `find_uncited_claims` |
| support checks | the paper's own bibliography, resolved with abstracts | `check_support` |
| missing work | a live literature search | `find_missing_work` |

That ordering is deliberate: when the search quota is spent, the review still
produces useful findings instead of failing.

---

## The files, and what each one does

### `provider/llm_backend.py`

A `Protocol` with exactly one method:

```python
async def complete_json(system, user, schema, schema_name, max_tokens) -> dict
```

Every model call in the codebase returns JSON matching a schema the caller
supplies. There is deliberately **no free-text completion** - a backend that
could return prose would invite someone to parse it.

The schema travels with the request because the schema *is* the safety
mechanism: the support schema requires a `quote` field, so with constrained
decoding the model literally cannot emit a verdict without one.

### `provider/openai_provider.py`

The real backend, talking to OpenAI's chat completions API.

| Function | What it does |
|---|---|
| `complete_json()` | build request, check cache, call, parse |
| `_post()` | HTTP with retries and rate-limit backoff |
| `_retry_after()` | honours the `retry-after` header, capped |
| `_content_of()` | pull the answer out of the response |
| `_parse()` | validate it is a JSON object |

`strict: true` turns on constrained decoding, so the model cannot produce a
response that violates the schema. Temperature is `0` because every call is a
judgement, not writing - two runs over the same paper should agree.

`_content_of()` handles two awkward cases: content arriving as a list of parts
rather than a string, and `finish_reason == "length"`, which means the answer
was cut off. A truncated response is raised as an error rather than parsed,
because a valid-but-incomplete answer would silently become an empty finding
list that looks like a clean review.

### `provider/stub_llm_provider.py`

An offline backend returning canned answers, or an empty response shaped to
the requested schema. It records every call so tests can assert what was
actually asked. With no API key configured, this is what gets wired in - so the
whole app runs, and the review returns an empty but well-formed result.

### `provider/sentence_provider.py`

Splits blocks into sentences **in code**, not by asking the model.

| Function | What it does |
|---|---|
| `for_document()` | every block → sentences |
| `for_block()` | one block → sentences with offsets and attached citations |
| `_flatten()` | inline nodes → plain text, remembering where each node sat |
| `_spans()` | find sentence boundaries |
| `_is_false_break()` | reject fake sentence ends |
| `_is_reportable()` | skip fragments under `MIN_REPORTABLE_CHARS` |

Each `Sentence` carries `block_id`, `index`, `start`, `end`, `text`, and
`ref_ids` - the citations that fall inside its character range.

**Why this is in code.** If the model chose the sentences, a finding could
point at text that is not in the paper. Because sentences are derived, every
finding has a real anchor a reader can check. On our test paper, 0 of 189
findings had a span mismatch.

`_is_false_break()` handles abbreviations - "et al." and "Fig. 2" are not
sentence ends. `ABBREVIATIONS` and the `INITIAL` pattern catch the common ones.

### `provider/support_provider.py` - the grounded pass

For one claim and one cited source, ask: does the abstract support this?

| Function | What it does |
|---|---|
| `check()` | send claim + abstract, get quote + grade, verify the quote |
| `_final_grade()` | downgrade to `insufficient_evidence` if the quote failed |
| `quote_is_verbatim()` | is the quote really in the abstract? |
| `normalise_for_matching()` | whitespace and case only |

The four grades: `supports`, `partially_supports`, `not_supported`,
`insufficient_evidence`.

**The verification is deliberately strict.** `normalise_for_matching()`
collapses whitespace and lowercases, and nothing else. It does not do fuzzy
matching, because a fuzzy match would accept a paraphrase, and a paraphrased
"quote" is exactly the thing being guarded against.

`MIN_QUOTE_CHARS` (12) rejects trivially short quotes - a three-word fragment
appears in almost any abstract and verifies nothing.

References with no abstract return `None` before any model call. There is
nothing to check against, and judging from a title alone is the failure this
design exists to prevent.

### `provider/claim_provider.py` - finding uncited claims

| Function | What it does |
|---|---|
| `find_uncited_claims()` | sentences → the ones that state a fact but cite nothing |
| `_batches()` | group sentences, `MAX_SENTENCES_PER_CALL` = 20 |
| `_judge()` | one model call per batch |

The model answers with **indices into the batch**, never with text. An index
outside the batch is discarded. This is what stops it inventing a sentence.

`limit` allows early stopping: once enough claims are found, remaining batches
are skipped. Without it, a 438-sentence paper cost 22 calls to keep 12 results.

### `provider/discovery_provider.py` - finding missing work

For a claim with no citation, search the literature for works that could
support it.

| Function | What it does |
|---|---|
| `find_missing_work()` | claim → real candidate sources |
| `_judge()` | ask the model which candidates are actually relevant |
| `_identifier()` | pull a DOI or OpenAlex id from a record |
| `already_cited_identifiers()` | so we do not suggest what is already cited |

The candidates come **from the search API**, never from the model. The model
only filters and explains. That is the difference between a suggestion and a
hallucination.

### `provider/review_provider.py`

The orchestrator. Owns the sequence and the anchoring, and contains no
judgement of its own.

| Function | What it does |
|---|---|
| `review()` | run the enabled passes, assign finding ids |
| `_check_support()` | pass over every (sentence, cited reference) pair |
| `_find_uncited_claims()` | claim pass, then discovery |
| `_blocks_that_never_cite()` | blocks to skip |
| `_worst()` | worst grade among several sources on one sentence |
| `_support_message()` | the sentence shown to the user |

**Only problem grades become findings.** `PROBLEM_GRADES` is
`{not_supported, partially_supports}`. A citation the source supports is the
normal case; reporting it would bury the few that matter.

**`NON_CITING_BLOCK_KINDS`** = `{abstract, caption, heading, formula}`. By
academic convention abstracts do not carry citations, so every factual sentence
in one looks like a missing citation and none of them are. On the first real
paper this produced 4 bad findings out of 12 - the fastest way to teach a
researcher to ignore the other 8.

**`DISCOVERY_BUDGET_SECONDS`** (25s) caps the discovery pass. Losing it costs
nothing structural: those claims still report as `uncited_claim`, just without
suggested sources. It exists because discovery is the only part depending on an
outside service, and its failure mode is not an error but a long silence -
measured at 33 seconds for a single call that returned nothing when OpenAlex
was out of quota.

Evidence is grouped **per sentence**, not per reference: a sentence citing
three works is one claim to a reader, not three findings.

### The last gate

`Finding.is_grounded` is enforced as the final step of both passes:

- an `unsupported_claim` survives only if some evidence carries a **verified
  quote**
- a `missing_citation` survives only if some suggestion carries a **real
  identifier**
- an `uncited_claim` is always grounded - it makes no external claim

Anything else is discarded, however confident the model was.

---

## The route

### `POST /papers/{paper_id}/review`

Query flags: `check_support`, `find_uncited_claims`, `find_missing_work`.

1. Load the document from the stored revision
2. Load references from `library.json` - **not** by re-resolving
3. Run the enabled passes
4. Return findings plus a summary

**A performance bug worth recording.** This route used to call `resolve_all()`
on every request, re-resolving every reference before a single claim could be
judged. With a warm cache that looked free; with a cold one it was 38 lookups
against a database that was out of quota. A review that should take 20 seconds
took over four minutes, all of it rebuilding an answer already on disk. It now
reads the library and makes **no external calls except to the model**.

`review_concurrency` (12) bounds how many model calls run at once. The wall
clock of a review is essentially "one call per cited claim, divided by this".

---

## Real measured numbers

On a 335-sentence paper with 51 citations to check:

```
review, no discovery : 16.3s
full review          : 42.6s
findings: 20  |  citations checked: 51  |  references without abstract: 12
```

Responses are cached on the exact request body, so a second run over an
unchanged paper is instant.

---

## Known limits

- Some findings flag the authors' own contribution claims. The model sees
  sentences in isolation, so "we propose X" can read as an uncited assertion.
  Fixing it properly means sending paragraph context.
- 12 of 38 references had no abstract and were skipped rather than guessed at.
  That number is reported in the summary.
