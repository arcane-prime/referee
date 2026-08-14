# Stage 4 — Agentic Editing in Natural Language

The plan for the last capability: letting a researcher improve their paper by
instruction, without the tool ever breaking their citations.

Nothing in this document is built yet. It is the agreement to build against.

---

## 1. What the brief actually asks for

From the assessment, capability 3:

> Let the user improve the paper by instruction. For example: "add more
> citations to the introduction", "find me more citations that support the
> methodology", or "make the intro shorter". Every edit should keep the paper
> intact:
>
> - Existing citations survive. Nothing is dropped silently.
> - Any new claim carries a real citation, with the source it came from.
> - Citations stay attached to the right context and meaning when text moves or
>   shrinks.
> - Show the changes for the user to approve, then export the revised paper.

And separately, two things it calls non-negotiable:

> peer review grounded in real, linkable sources and never hallucinated, and
> edits that never silently break the paper's citations or structure.

So stage 4 is graded on one thing above all: **an edit must be unable to
silently damage the paper.** Not unlikely to. Unable to.

---

## 2. What natural language can and cannot change

This is the question that decides the whole design, and the answer was fixed
back in stage 1 when the document model was chosen. From `domain/document.py`:

> The LLM writes TextRun content and nothing else. Every other inline is
> selected, moved, or removed with the user's approval, never authored.

Written out per node type:

| Node | LLM may author it | May move | May be added | May be removed |
|---|---|---|---|---|
| **TextRun** | **yes — the only one** | yes | yes | yes |
| **CiteNode** | never | yes | only from the library | only with the loss shown |
| **XRefNode** | never | yes | no | only with the loss shown |
| **MathNode** | never | yes | no | only with the loss shown |

Two clarifications, because "fixed" is easy to over-read:

**Citations are not frozen in place.** They must be able to move — the brief
explicitly requires that citations "stay attached to the right context and
meaning when text moves or shrinks". If a three-sentence passage becomes one
sentence, its citations have to travel with the claim they support. What is
forbidden is *authoring* them: their `id`, `ref_ids`, and the work they point
at are never produced by a model.

**Figures, tables and equations get the same protection for free.** The brief
does not require it, but `XRefNode` and `MathNode` ride the same mechanism as
`CiteNode`, so "make the intro shorter" cannot quietly drop a reference to
Table 2 or mangle a formula either.

---

## 3. The mechanism: deflate, edit, inflate

The core trick, and the reason citation preservation is structural rather than
a request in a prompt.

**The model never sees a block.** It sees the block's TextRuns with every
non-text node replaced by an opaque placeholder.

Deflate the block:

```
inlines:  [TextRun("Transformers dominate NLP "),
           CiteNode(id="c_4", ref_ids=["ref_12"]),
           TextRun(". Recent work extends this to vision "),
           CiteNode(id="c_5", ref_ids=["ref_13","ref_14"]),
           TextRun(", with results in "),
           XRefNode(id="x_2", label="Table 2"),
           TextRun(".")]

sent to the model:
  "Transformers dominate NLP [[c_4]]. Recent work extends this to vision
   [[c_5]], with results in [[x_2]]."
```

The model returns shortened prose, and the placeholders are part of its
contract:

```
  "Transformers dominate NLP and now vision [[c_4]] [[c_5]] (see [[x_2]])."
```

Inflate: split on the placeholders and rebuild the inline list using **the
original node objects** — same `id`, same `ref_ids`, same coords. The model
decided where `[[c_4]]` sits. It could not touch what `[[c_4]]` is.

What this buys, in order of importance:

1. **A citation cannot be reworded, retargeted or invented.** It was never text
   in the model's input, so there is nothing for it to get wrong.
2. **A citation follows its claim** when the surrounding prose shrinks, which
   is the "stays attached to the right context" requirement.
3. **A dropped citation is detectable.** The set of placeholders sent out and
   the set returned are compared. A missing one fails the edit rather than
   applying it.

Failure handling is deliberate: if the model returns text with a placeholder
missing, malformed, or duplicated, the operation is **rejected**, not repaired.
A repaired edit is a guess about intent. The user is told the model produced an
edit that would have dropped a citation, which is a true and useful thing to
show them.

---

## 4. The invariant check

The placeholder round-trip is the mechanism. This is the independent audit that
does not trust it.

`Document.ref_id_counts()` already exists and returns `{ref_id: times cited}`.
The check compares that dict before and after a proposed edit:

| Operation | Permitted change to counts |
|---|---|
| `rewrite_block`, `shorten_block` | **identical** — no key added, removed, or changed |
| `add_citation` | counts may only **increase** |
| `delete_block` | may decrease, but every lost `ref_id` is named in the diff |

Any operation whose actual delta does not match its declared permission is
vetoed and never reaches the user.

This is two independent guards on the same property, on purpose. The
placeholder round-trip is per-block and structural; the count check is
whole-document and arithmetic. A bug in one does not disable the other.

### Where new citations may come from

For `add_citation`, the invariant is not just "counts went up". A new
`CiteNode` may only point at a library entry where this holds — already
implemented in `domain/library.py`:

```python
@property
def can_be_cited_by_the_agent(self) -> bool:
    return (self.provenance == "fetched_from_api"
            and not self.resolution.external_ids.is_empty)
```

The agent can only cite a work that came back from OpenAlex or Semantic Scholar
carrying a real external id. **A fabricated citation cannot satisfy that check
no matter what the model writes**, which is what makes "never hallucinated" a
property of the type system rather than a hope about the prompt.

---

## 5. Where the LLM sits

The brief grades "no single giant prompt doing everything". Three narrow calls,
each with a schema, and deterministic code between them.

**1. Planner** — command in, typed plan out.

```
"make the intro shorter"
  -> {intent: "shorten",
      scope: {section: "Introduction"},
      operations: [{kind: "shorten_block", block_id: "b_4", target_ratio: 0.7},
                   {kind: "shorten_block", block_id: "b_5", target_ratio: 0.7}]}
```

It chooses *targets*. It writes no prose. Its whole output is a small typed
object, so a bad plan is a validation error rather than a corrupted paper.

**2. Writer** — one call per block, placeholder text in, placeholder text out.
It sees a single paragraph and has no access to the document, the library, or
the plan.

**3. Citation finder** — reuses `discovery_provider.py` from the review module,
which already searches OpenAlex and Semantic Scholar and returns real records.
Nothing new is needed to avoid fabricating sources; that module already only
returns what an API gave it.

Everything else is ordinary code: resolving "the introduction" to block ids,
deflating and inflating, running the invariants, building the diff, writing the
revision.

---

## 6. Module layout

`app/modules/editing/`, following the same `api` / `provider` / `dto` split as
the other three modules.

```
provider/
    placeholder_provider.py   deflate / inflate / integrity check   (pure)
    invariant_provider.py     ref_id_counts veto                    (pure)
    operation_provider.py     the typed operations, apply()         (pure)
    diff_provider.py          block-level before/after for the UI   (pure)
    plan_provider.py          command -> EditPlan                   (LLM)
    writer_provider.py        block prose rewrite                   (LLM)
    edit_provider.py          orchestrator
    revision_provider.py      writes rev_N+1.json on approval
api/
    edit_routes.py, dependencies.py
dto/
    edit_dto.py
```

Four of the eight providers are pure functions over the domain model with no
I/O, which is what makes the citation-safety core testable without a network,
an API key, or a model.

---

## 7. Domain models to add

New file `app/domain/edit.py`:

- `EditOperation` — discriminated union on `kind`, mirroring the `Inline`
  pattern: `ShortenBlock`, `RewriteBlock`, `AddCitation`, `InsertBlock`,
  `DeleteBlock`
- `EditPlan` — the command, the resolved scope, and the operations
- `BlockPatch` — one block's before and after inline lists
- `CitationDelta` — `added`, `removed`, `moved` ref ids for one patch
- `RevisionProposal` — the patches plus the whole-document delta, **not yet
  applied**
- `EditOutcome` — applied / rejected, with the reason when rejected

`RevisionProposal` existing as its own type is the point: a proposal is a value
the user can be shown and can decline, not a side effect that already happened.

---

## 8. Storage

One addition, already flagged as required in `CODEBASE.md` §5:

```
data/papers/<paper_id>/
    original.pdf      untouched, always
    grobid.tei.xml    raw parser output
    library.json      NEW - append-only, every reference ever known
    rev_0.json        the extraction
    rev_1.json        after the first approved edit
```

`library.json` has to exist before stage 4 because the edit invariant checks
new citations against the library, and recomputing it would mean re-running
resolution and spending API quota on every edit. `Library` is already
documented as append-only: a reference introduced by an edit the user later
rejects is kept, so no revision can ever point at a reference that vanished.

Revisions stay append-only too, which makes undo "read a smaller number".

---

## 9. Routes

```
POST /papers/{id}/edit/plan       command -> RevisionProposal (nothing written)
POST /papers/{id}/edit/apply      approve a proposal -> rev_N+1
GET  /papers/{id}/export.tex      LaTeX + bibliography
```

Plan and apply are deliberately two calls. The proposal is computed, checked
and returned; only a second, explicit request writes anything. That is the
"show the changes for the user to approve" requirement expressed in the API
shape rather than in the UI alone.

---

## 10. Frontend

The split view built for stage 3 already gives the shape: parse on the left,
agent on the right. Editing adds a command box and a diff to the right pane.

- A text input for the instruction
- The returned proposal rendered as block-level before/after, with citation
  chips visible in both so a moved citation is something you can see
- Per-operation **Approve** / **Reject**, and an explicit apply
- After apply, the left pane re-renders at the new revision

A rejected proposal writes nothing and costs nothing.

---

## 11. Export

`citeproc-py`, in `requirements.txt`, reading real `.csl` style files.

The document becomes LaTeX: sections, paragraphs, and `\cite{ref_id}` where
each `CiteNode` sits. The library becomes the bibliography. The style comes
from the detected `CitationStyle`, or from the user's pick when detection
returned `unknown`.

This is what `domain/csl.py` has claimed from the start and is currently the
one aspirational note in the codebase:

> All printing is done by Pandoc citeproc from a .csl stylesheet. There are no
> string templates for citations anywhere in this codebase and there should
> never be one.

Stage 4 makes that true. The characters `[12]` still exist nowhere in stored
data; they are produced at render time, which is also why one document can
print as IEEE or APA without the data changing.

---

## 12. Tests

The valuable ones need no network and no model, because the safety core is
pure:

- **Round-trip**: deflate then inflate with no change returns an identical
  block, node ids included
- **Move**: a reordered placeholder string moves the node and preserves its
  `ref_ids`
- **Drop is caught**: a returned string missing a placeholder raises rather
  than applying
- **Duplicate is caught**: a returned string with a placeholder twice raises
- **Invariant veto**: a `shorten_block` whose counts changed is rejected
- **Fabrication is impossible**: `add_citation` pointing at a
  `parsed_from_pdf` reference is refused by `can_be_cited_by_the_agent`
- **Plan validation**: a plan naming a block id that does not exist fails
  cleanly

A stub LLM backend already exists (`stub_llm_provider.py`) and gives the
orchestrator an offline path, exactly as it does for the review module.

---

## 13. Build order and scope

Agreed scope given the deadline: **the edit loop through approval, then the
docs.** Export stays simple; the system-design writeups are the brief's
highest-weighted item and are not yet written.

1. `library.json` persistence — prerequisite
2. `domain/edit.py`
3. `placeholder_provider.py` **+ its tests** — the load-bearing piece, built
   and proven before anything calls a model
4. `invariant_provider.py` + tests
5. `operation_provider.py`
6. `plan_provider.py`, `writer_provider.py`
7. `edit_provider.py`, `diff_provider.py`, `revision_provider.py`
8. Routes and DTOs
9. Frontend command box and diff
10. Export: LaTeX + citeproc-py
11. `docs/01-citation-parsing.md`, `docs/02-agent.md`, `README.md`

Steps 3 and 4 come before any LLM work on purpose. If the citation-safety core
is not provably correct offline, nothing built on top of it can be trusted, and
it is the part the brief calls non-negotiable.

---

## 14. Known limitations to state honestly

Better written down now than discovered by a reviewer:

- **Sentence-level citation reattachment is best-effort.** When a paragraph is
  heavily rewritten the citation lands where the model put the placeholder. We
  guarantee it survives and stays in its block; we do not guarantee it is still
  beside the exact clause a human would have chosen.
- **No cross-block moves in the first version.** An operation edits one block.
  Merging or splitting paragraphs is a later operation type.
- **Export is LaTeX, not the original PDF layout.** The brief recommends
  exactly this, but it is worth saying plainly that the round trip is
  structure-preserving, not pixel-preserving.
- **The review step is currently rate limited** by the free Cerebras tier at 5
  requests per minute, and editing adds calls on the same budget. The pacing
  fix is known and not yet applied.

---

## 15. The one-sentence version

The model rewrites prose with the citations replaced by opaque tokens it cannot
read, and code puts the real citation nodes back where those tokens ended up —
so an edit that damages a citation is not something we detect and fix, it is
something the pipeline cannot express.
