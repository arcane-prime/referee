# Edit — changing the paper with natural-language commands

**Module:** `backend/app/modules/editing/`
**Routes:** `GET /papers/{id}/document`, `POST /papers/{id}/edit/plan`,
`POST /papers/{id}/edit/apply`

---

## What this feature does

The researcher types an instruction in plain English — *"make the introduction
shorter"* — and gets back a set of proposed changes, shown as before/after per
paragraph. Nothing is written until they approve it. On approval a new revision
is saved and the old one is kept.

---

## The problem this stage has to solve

An AI rewriting a paragraph can very easily destroy a citation. It can drop it,
reword it, merge two into one, or invent a new one that looks plausible. The
brief calls this non-negotiable:

> edits that never silently break the paper's citations or structure

"Silently" is the important word. It is not enough to usually get it right. We
need it to be **impossible to express** a damaged citation, and where that
fails, **impossible to apply one without saying so**.

---

## The mechanism: deflate → edit → inflate

**The model never sees a paragraph.** It sees the prose with every citation,
cross-reference and formula replaced by an opaque token.

Deflate the block:

```
inlines:  TextRun("Transformers dominate NLP ")
          CiteNode(id="c_4", ref_ids=["ref_12"])
          TextRun(". Recent work extends this to vision ")
          CiteNode(id="c_5", ref_ids=["ref_13","ref_14"])
          TextRun(", with results in ")
          XRefNode(id="x_2", label="Table 2")
          TextRun(".")

sent to the model:
  "Transformers dominate NLP [[c_4]]. Recent work extends this to vision
   [[c_5]], with results in [[x_2]]."
```

The model returns shortened prose, keeping the tokens:

```
  "Transformers dominate NLP and now vision [[c_4]] [[c_5]] (see [[x_2]])."
```

Inflate: split on the tokens and rebuild the list using **the original node
objects** — same id, same `ref_ids`, same coordinates.

The model chose *where* `[[c_4]]` sits. It could not touch *what* `[[c_4]]` is.

### What this buys, in order of importance

1. **A citation cannot be reworded, retargeted or invented.** It was never text
   in the model's input, so there is nothing for it to get wrong.
2. **A citation follows its claim** when prose shrinks — which the brief
   requires. A citation frozen in place would end up beside a sentence that no
   longer exists.
3. **A dropped citation is detectable.** Compare the tokens sent with the
   tokens returned.

### Failure is refusal, not repair

If the model returns text with a token missing, duplicated, or invented, the
operation is **rejected**. We do not put the citation back where we think it
belongs — that would be guessing at intent. The user is told which markers were
lost, for which paragraph.

---

## The second, independent check

The token round-trip is per-block and structural. The invariant check is
whole-document and arithmetic. Two guards on the same property, so a bug in one
does not disable the other.

`Document.ref_id_counts()` returns `{ref_id: how many times cited}`. We compare
it before and after:

| Operation | Allowed change |
|---|---|
| `shorten_block`, `rewrite_block` | **identical** — nothing added or removed |
| `add_citation` | may only **increase** |
| `delete_block` | may decrease, but every lost id is named in the diff |

An operation whose real delta does not match its declared rule is vetoed and
never reaches the user.

### Where a new citation may come from

For `add_citation`, "counts went up" is not enough. The new `CiteNode` must
point at a library entry passing this test, which already existed in the domain
model:

```python
@property
def can_be_cited_by_the_agent(self) -> bool:
    return (self.provenance == "fetched_from_api"
            and not self.resolution.external_ids.is_empty)
```

The agent may only cite a work that came back from OpenAlex or Semantic Scholar
carrying a real external id. **A fabricated citation cannot satisfy that check
no matter what the model writes** — an invented id is not in the library, and a
reference merely parsed from the user's own PDF has provenance
`parsed_from_pdf` and fails the second half.

---

## Where the LLM sits — two small calls, not one big prompt

**1. The planner** — command in, typed plan out. It chooses *targets*. It
writes no prose.

```
"make the intro shorter"
  → intent: "shorten the introduction"
    operations: [ {kind: shorten_block, block_id: "s0.p0", target_ratio: 0.7} ]
```

**2. The writer** — one call per block. Token text in, token text out. It sees a
single paragraph and knows nothing about the document, the library, or the plan.

Everything else is ordinary code: resolving which blocks, deflating and
inflating, running the invariants, building the diff, writing the revision.

---

## The files, and what each one does

### `provider/placeholder_provider.py` — the safety core

Pure functions. No network, no model, no I/O.

| Function | What it does |
|---|---|
| `deflate()` | inline list → text with tokens + a map of token → node |
| `inflate()` | edited text + map → rebuilt inline list |
| `verify()` | are all tokens present, none invented, none duplicated? |
| `reordered()` | which tokens changed position |
| `token_for()` | `"c_4"` → `"[[c_4]]"` |
| `DeflatedBlock.tokens` / `.order` | the token set, and their sequence |

`verify()` raises `PlaceholderMismatch` with a plain-English reason. Its three
checks are ordered by how much damage each represents: **missing** (a citation
would be dropped), **invented** (fabrication wearing our syntax), **duplicated**
(one citation would become two).

The token carries the node's own id, not an index — an index would be stable
only until something reordered, and a mismatch would then be silently wrong
instead of loudly wrong.

`deflate()` also rejects a block holding two nodes with the same id. That should
be impossible, but the whole guarantee is keyed on ids, so the one case that
would break it silently is checked rather than assumed.

### `provider/invariant_provider.py` — the audit

| Function | What it does |
|---|---|
| `ref_counts()` | inline list → `{ref_id: count}` |
| `compare()` | two count maps → what was added and removed |
| `enforce()` | does the change match what this operation may do? |
| `check_citable()` | may the agent cite this reference at all? |
| `document_delta()` | whole-document before/after |

`compare()` counts **multiplicity**, not membership: citing `ref_12` twice and
citing it once are different claims about the paper.

`COUNT_RULES` lives in `domain/edit.py`, next to the operations, so adding an
operation forces a decision about what it may do to citations. An operation with
no rule is **refused**, not defaulted — "may this drop citations?" is not a
question anyone should get to leave blank.

### `provider/operation_provider.py` — the typed operations

Pure functions from a block to a `BlockPatch`. Every one runs both guards
before returning.

| Function | What it does |
|---|---|
| `apply_text()` | shorten/rewrite: deflate → inflate → enforce → patch |
| `add_citation()` | insert a new `CiteNode`, enforce, patch |
| `delete_block()` | remove a block, reporting every citation it takes with it |
| `_insert_before_final_stop()` | place the marker before the full stop |

`_insert_before_final_stop()` is small but deliberate: *"…as shown in prior work
[12]."* is where a citation belongs; *"…as shown in prior work. [12]"* is not a
sentence anyone wrote. It is typographic judgement, and it lives in code because
it is deterministic.

A new `CiteNode` carries exactly one `ref_id`. Grouped citations like `[12, 13]`
are something the author wrote and the parser preserved; the agent adding one
source at a time keeps each insertion individually reviewable.

### `provider/plan_provider.py`

| Function | What it does |
|---|---|
| `plan()` | command + document → an `EditPlan` |
| `_prompt()` | build the block outline shown to the model |
| `_clean()` | drop null fields before validation |

Blocks are offered as id, kind, citation count and a short preview — not full
prose. The planner is choosing *where* to work.

Operations naming a block that does not exist are dropped rather than failing
the request. A model inventing `b_99` is a plan that cannot run, not a reason to
lose the operations it got right.

`MAX_OPERATIONS` (8) caps how much one command may change. "Rewrite my paper" is
a request this tool should decline to satisfy in one unreviewable step.

`PLAN_MAX_TOKENS` (4096) is raised above default because this is the largest
prompt in the codebase.

### `provider/writer_provider.py`

| Function | What it does |
|---|---|
| `shorten()` | rewrite to about N words, keeping every marker |
| `rewrite()` | apply a free-text instruction to one paragraph |
| `_write()` | the actual model call |

The system prompt asks it to preserve markers — but **nothing depends on it
obeying**. The prompt is a request; the round-trip check is the guarantee.

One rule guards something the marker check cannot see: *"do not write citations
yourself in any other form"*. A model writing `(Smith, 2019)` as ordinary prose
breaks no marker, but puts an unverifiable citation into the paper as plain
text.

The word target is computed in code, because models handle "about 40 words"
better than "70% of the original length".

### `provider/edit_provider.py` — the orchestrator

| Function | What it does |
|---|---|
| `propose()` | plan, run each operation, collect patches and refusals |
| `apply()` | re-verify everything, write the next revision |
| `_run()` | dispatch one operation to the right handler |
| `_verify_against_disk()` | is this patch still valid against the stored document? |
| `_write_patch()` | replace or remove the block |

**`propose()` writes nothing.** It loads a revision, asks the planner, runs each
operation, and returns what *would* happen.

**A refused operation does not fail the request.** It becomes a
`RejectedOperation` carrying the reason, and the operations that succeeded are
still offered. An edit that quietly did less than it claimed is the failure this
stage exists to prevent; an edit that did four of five things and said so is
useful.

**`apply()` re-checks everything rather than trusting what it was handed.** The
proposal travels to the browser and back, so by the time it returns it is user
input. Three things are verified:

1. the base revision still matches (nothing changed underneath)
2. every targeted block still holds **exactly** the inlines the patch was
   computed from — a full structural comparison, not a hash
3. the citation counts still satisfy the operation's rule

A tampered `after` list that dropped a citation fails check 3. A stale proposal
fails checks 1 and 2.

New citation node ids are minted as `c_e1`, `c_e2` from the document's own
counter, so an id created by an edit can never collide with one the parser
assigned.

### `provider/revision_provider.py`

| Function | What it does |
|---|---|
| `load()` | read a revision (latest by default) |
| `save()` | write `rev_N+1.json` |
| `latest_number()` | highest revision on disk |
| `available()` | all revision numbers |
| `load_library()` | delegate to the shared library provider |

**Revisions are append-only.** `save()` writes a new file and never touches the
old one, so undo is pointing at a smaller number rather than a reverse operation
that has to be correct. The original PDF is never rewritten at all.

The latest revision is read off the directory rather than tracked in a counter —
the files are the truth.

---

## The domain models — `domain/edit.py`

| Model | What it is |
|---|---|
| `ShortenBlock`, `RewriteBlock`, `AddCitation`, `DeleteBlock` | the typed operations, a discriminated union on `kind` |
| `EditPlan` | the command, the scope, and the operations |
| `BlockPatch` | one block's before and after, plus its citation delta |
| `CitationDelta` | `added`, `removed`, `moved` |
| `RejectedOperation` | a refused operation and why |
| `RevisionProposal` | the patches, **not yet applied** |
| `AppliedRevision` | what actually got written |

`CitationDelta` separates **moved** from added and removed on purpose. A
citation moving is normal during a shorten; one being added or removed is a
decision the user must see. Collapsing all three into "changed" would bury the
only two cases that matter.

`RevisionProposal` existing as its own type is the point: a proposal is a value
the user can be shown and can decline, not a side effect that already happened.

---

## The routes

| Route | What it does |
|---|---|
| `GET /papers/{id}/document` | read the paper at the latest or a specific revision |
| `POST /papers/{id}/edit/plan` | command → proposal. **Writes nothing.** |
| `POST /papers/{id}/edit/apply` | approved blocks → `rev_N+1` |

Both edit routes return HTTP 200 even when everything was refused, because a
refusal is a successful answer to "what would this command do". Only `apply()`
raises: `EditConflictError` (409) when the paper moved underneath, and
`EditRefusedError` (422) when the edit itself was unacceptable.

The apply body carries the whole proposal plus a list of approved block ids, so
a researcher can accept two changes and drop the third.

---

## Tests

The safety core is pure, so all of it is tested offline in under a second.
The load-bearing tests:

- `test_the_model_never_sees_a_ref_id` — asserts the negative the design rests on
- round trip with no change rebuilds the block **exactly**
- `inflate` reuses the **original node objects** (checks identity, not equality —
  an equal-looking rebuilt node would pass while proving the opposite)
- a citation may move and keeps its `ref_ids`
- dropped / invented / duplicated markers each raise, naming the marker
- an empty rewrite loses everything and is refused
- formulas and cross-references get the same protection
- `add_citation` pointing at a `parsed_from_pdf` reference is refused
- a tampered proposal is refused on apply, and nothing is written
- a stale proposal raises a conflict

---

## Verified end to end on a real paper

```
BEFORE  rev 1 | citations: 62
PLAN    1 change ready, 0 refused          (7.4s)
APPLY   Applied 1 change as revision 2. Revision 1 unchanged on disk.
AFTER   rev 2 | available: [0, 1, 2]

CITATIONS IDENTICAL: True (62 -> 62)
s0.p2: 691 -> 286 chars   (59% shorter)
  cites before: [[ref_1, ref_14]]
  cites after : [[ref_1, ref_14]]
```

---

## Known limits

- An operation edits **one block**. No merging or splitting of paragraphs.
- A citation is guaranteed to survive and stay in its block, but after a heavy
  rewrite it may not sit beside the exact clause a human would have chosen.
- The agent cannot add citations to a paper whose references were never
  resolved, because the library holds nothing with an external id. The UI says
  so rather than letting the refusal look like a bug.
