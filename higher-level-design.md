# High-level design

**Diagram:** https://excalidraw.com/#json=C64ZG4E43_vYbprMB0VO6,ysppSaCXiyz4yZfaq4DhZA

*(the board holds two diagrams - the first is from an earlier interview, the
second one is this assignment)*

If you would rather read than look at boxes, everything the diagram shows is
written out below. Start here, then go to the per-feature documents in this
folder for detail.

---

## The problem

A researcher has finished a paper and wants to strengthen it before submitting.
Three things they need help with:

1. **Did I miss relevant work?**
2. **Do the papers I cited actually say what I claim they say?**
3. **Can I tighten this section without breaking anything?**

The last one is where existing tools fail. Hand a paper to a chatbot and ask it
to shorten a paragraph, and it will happily return prose with a citation
deleted, reworded, or invented. A researcher cannot use a tool they have to
proofread that closely.

**So the whole system is built around one promise: an AI edit can never silently
change your citations.**

---

## The pieces

**The browser** - the researcher's screen. One page, split into two: the paper
on the left, the AI on the right.

**The Referee API** - a Python server holding all the logic. It talks to four
outside services and stores everything as plain files.

**File storage** - one folder per paper. No database. A paper is a small amount
of data used by one person, so a database would be machinery bought for a
problem this does not have.

**Four outside services**

| | What it is for |
|---|---|
| **GROBID** | turns a PDF into structured XML. Runs in Docker, or use a free public one |
| **OpenAlex** | a free database of academic papers - the main reference lookup |
| **Semantic Scholar** | a second database, used as backup and for abstracts |
| **OpenAI** | the language model that reviews and rewrites |

Nothing in the code names a vendor except one wiring file. Swapping the language
model provider, or the PDF parser, means writing one new file.

---

## How a paper moves through it

**1. Upload.** The PDF is saved and never touched again. Whatever happens next,
the researcher's original file is always there to download.

**2. Parse** *(under a second)*. GROBID converts the PDF to XML; the app turns
that into its own document format - sections, paragraphs, citations. Saved as
revision 0.

**3. Check the references** *(about 30 seconds for 40 references)*. Every entry
in the bibliography is looked up in OpenAlex, falling back to Semantic Scholar.
For each one we record whether we found it, its DOI, and its abstract.

Steps 2 and 3 are **two separate requests**, and that is a deliberate design
choice. Parsing takes under a second; checking references takes half a minute
because each one is a call to a free public database that rate limits. If they
were one request the researcher would stare at a spinner for thirty seconds
while a finished parse sat on the server. Split, the paper appears immediately
and the reference panel fills in underneath.

**4. Review** *(on request)*. The language model reads the paper and reports
problems. It can only judge a claim against an abstract that was actually
fetched in step 3.

**5. Edit** *(on request)*. The researcher types an instruction. The app returns
a preview of what would change. Nothing is saved until they approve it, and
approving writes a **new** version rather than overwriting the old one.

**6. Export** *(any time)*. Any version can be downloaded as LaTeX, with the
bibliography formatted from a real citation stylesheet.

Steps 4, 5 and 6 all read files that steps 2 and 3 already wrote. None of them
re-parses the PDF or re-queries a database.

---

## The one idea everything rests on

**A paragraph is not stored as a sentence of text.**

Most tools would store this:

> Transformers dominate NLP [12]. Recent work extends this to vision [13, 14].

as exactly that - one string. Referee stores it as a *list of pieces*:

```
a piece of text:   "Transformers dominate NLP "
a citation:        points at reference 12
a piece of text:   ". Recent work extends this to vision "
a citation:        points at references 13 and 14
a piece of text:   "."
```

The characters `[12]` are stored **nowhere**. A citation is an object that
points at a bibliography entry. The `[12]` a reader sees is printed at the last
moment - by the screen when displaying, and by the citation formatter when
exporting. That is also why the same paper can print as IEEE or APA without the
stored data changing at all.

### Why this matters for editing

When the AI is asked to shorten a paragraph, it is not given the paragraph. It
is given the prose with every citation swapped for a meaningless placeholder:

```
given to the AI:     "Transformers dominate NLP [[c_4]]. Recent work
                      extends this to vision [[c_5]]."

the AI returns:      "Transformers dominate NLP [[c_4]] and now
                      vision [[c_5]]."
```

Then the app puts the **original citation objects** back wherever the
placeholders ended up.

The AI decided *where* the citation goes. It never had the ability to change
*what* the citation is - it never saw a reference id, a title, or an author.

If a placeholder comes back missing, duplicated, or invented, the edit is
**rejected**, and the researcher is told which one and in which paragraph. It is
not quietly repaired, because repairing it would mean guessing what the author
meant.

A second, separate check counts the citations before and after and compares them
against what that kind of edit was allowed to do. Shortening must leave the
count identical. Adding a citation may only increase it. Deleting a paragraph
may reduce it, but every lost reference is named in the preview.

Two independent guards on the same promise, so a bug in one does not disable the
other.

---

## The other rule: never invent a source

The same problem appears in reviewing. A language model asked "what work should
this paper cite?" will confidently produce a paper that does not exist.

Referee handles this structurally rather than by asking nicely:

- **Suggested sources come from the database, not the model.** The app searches
  OpenAlex and Semantic Scholar; the model only picks from what came back and
  explains why. It cannot suggest something it was not shown.
- **Every judgement must come with a quote.** When the model says a source only
  partly supports a claim, it must also return the sentence from that source's
  abstract it based that on. The app then checks, in ordinary code, that the
  quote really appears in the abstract. If it does not, the verdict is thrown
  away.
- **The model may only add a citation to a work a database returned.** A
  reference merely read off the user's own PDF is not enough - it has to have
  been found, with a real identifier.

So "it never makes things up" is not a hope about the prompt. It is a property
of what the model is physically able to reach.

---

## Nothing is overwritten

Three rules about what is written to disk:

**The original PDF is never modified.** Written once at upload, only ever read
afterwards.

**Every approved edit creates a new version.** Revision 0 is the original parse,
revision 1 is after the first accepted edit, and so on. Undo is just reading a
smaller number. You can export version 0 and version 3 and compare them to see
exactly what the AI changed.

**The reference list only ever grows.** Once a work has been found in a
database, it stays - even if the edit that discovered it was rejected. Otherwise
an older version of the paper could end up pointing at a reference that had
disappeared.

---

## When something breaks

Every outside service can fail without taking the app down.

| If this is unavailable | You lose | You keep |
|---|---|---|
| GROBID | uploading a **new** paper | everything else - review, edit, export |
| OpenAlex | - | Semantic Scholar picks up the search |
| Both databases | checking references, suggesting sources | the parsed paper, and review of uncited claims |
| The language model | review and editing | the parse, the references, and export |
| No API key at all | real review and editing | the app still runs, using an offline stub |

Two places have a time limit, because they depend on services outside our
control and their failure mode is not an error but a long silence: reference
checking gives up after 75 seconds, and the source-suggestion step after 25.
Both turn a hang into a bounded wait and an honest message.

Every failure is reported in words a researcher can act on, and the parsed paper
is never lost because something else went wrong.

---

## Being honest about what did not work

A tool like this is only useful if you can trust what it says, so the app
reports its own failures rather than hiding them:

- citation markers found in the text that could not be matched to any
  bibliography entry
- references whose text the parser could not understand - kept and shown
  verbatim rather than dropped
- references that were searched for and genuinely not found, each with a
  plain-English reason
- references with no abstract available, which are skipped rather than guessed
  at, with the count shown
- a citation style that could not be identified confidently, reported as
  "unknown" so the user picks

On one real test paper, 6 of 38 references failed to resolve. Each was checked
by hand: two had the journal name accidentally glued into the title by the
parser, one had no title at all, and three parsed perfectly but are simply
absent from the databases - a 1967 Soviet journal, a paper published too
recently to be indexed, and a poorly indexed one from 2009.

That number is reported as it is. A tool that quietly showed 38 of 38 would be
easier to demo and worth much less.

---

# The two system-design pieces

The assessment asks for the design of two things specifically. Both are written
out here end to end.

---

## Piece 1 - Citation parsing

**The job:** turn a PDF into citations that are structured, normalised, and
checkable - handling more than one citation style, and surfacing what could not
be parsed rather than dropping it.

### The pipeline

```
   PDF file
      │
      │  GrobidProvider          send the PDF to GROBID
      ▼
   TEI XML                       structured but generic markup
      │
      ├─ TeiProvider ──────────► walks the XML, builds sections and paragraphs
      │     │
      │     └─ InlineProvider ─► the hard part: turns mixed text+tags into
      │                          a LIST OF NODES, absorbing stray brackets
      │
      └─ ReferenceProvider ────► reads the bibliography into CSL-JSON
      │
      ▼
   Document (rev_0.json)  +  RawReference[]
      │
      │  StyleProvider           IEEE / APA / Nature / unknown
      ▼
      │
      │  ── separate request ──
      │
      │  OpenAlexProvider        search by DOI, else by title
      │  SemanticScholarProvider fallback + abstracts
      │  MatcherProvider         score 0-1, decide, collapse duplicates
      ▼
   Reference[] (library.json)    now carrying real DOIs and abstracts
      │
      │  bibliography_provider   citeproc + a real .csl file
      ▼
   formatted citations           "[12]" or "(Smith, 2019)"
```

### The intermediate representation

This is the part that matters. **A paragraph is a list of nodes, not a string.**

```
Block
 └── inlines[]
       TextRun    ordinary prose - the only thing an AI may write
       CiteNode   points at reference ids. Holds NO printed text
       XRefNode   a figure, table or equation reference
       MathNode   a formula
```

The printed marker `[12]` is stored **nowhere**. It exists only in
`raw_marker`, kept as a record of what the page said, and is regenerated at
display and export time.

Two consequences fall out of this, and both are why the model is shaped this
way rather than as text:

- an AI rewriting prose cannot delete a citation, because the citation was
  never part of the prose it was handed
- citation preservation becomes **countable** - `ref_id_counts()` returns
  `{ref_id: times cited}`, so "did this edit break anything?" is arithmetic
  rather than judgement

### Where CSL-JSON fits

`CSL-JSON` is the single canonical shape for citation data. Everything becomes
a `CSLItem`:

```
scraped out of the user's PDF   ──┐
                                  ├──► CSLItem ──► citeproc + .csl ──► printed
fetched from OpenAlex / S2      ──┘
```

The renderer never needs to know where a reference came from. No string
template anywhere in the codebase formats a citation - which is why the same
paper prints as IEEE, APA or Nature with no change to the stored data.

### Handling styles

`StyleProvider` samples the in-text markers and classifies them as numbered
(`[12]`) or author-year (`(Smith, 2019)`), returning a style plus a confidence.

Below the confidence threshold it returns **`unknown`** rather than guessing,
and the user picks at export time. A wrong guess is worse than an honest "I do
not know", because the user cannot tell it happened.

### Handling failures

Nothing is ever dropped silently:

| Failure | What happens |
|---|---|
| A reference whose fields would not parse | `raw` string kept verbatim, shown to the user, still searchable |
| A citation marker matching no bibliography entry | counted as **unlinked** and reported |
| A reference not found in any database | status `unresolved`, with a plain-English reason |
| A reference found but with no abstract | flagged; claims against it are skipped, not guessed |
| A citation style that is not clear | reported as `unknown` |

The delimiter problem is worth naming because it is where most of the
engineering went. GROBID marks `[12]` as just `12` inside a `<ref>` tag,
leaving the brackets outside as ordinary text. Left alone, the prose would
contain stray `[` and `]` that an AI edit could move or delete.
`InlineProvider` absorbs them into the citation node, and merges `[12, 13]` -
which GROBID reports as two separate refs with a comma between - back into one
citation act. On the test paper this yields **0 stray brackets across 58
citations**.

---

## Piece 2 - The agent

**The job:** turn a plain-English command into changes the user approves, and
review the paper against real sources - without ever inventing a citation or
damaging one.

### How a command becomes actions

```
   "make the introduction shorter"
      │
      ▼
   PlanProvider  ── LLM call #1 ──────────────────────────────────┐
      │   sees:   the paper as an OUTLINE (block ids, kinds,       │
      │           citation counts, short previews)                 │
      │   returns: typed operations. NO PROSE.                     │
      │                                                            │
      ▼                                                            │
   EditPlan                                                        │
      [ {shorten_block, s0.p3, 0.7}, {shorten_block, s0.p4, 0.7} ] │
      │                                                            │
      │  for each operation:                                       │
      ▼                                                            │
   ┌──────────────────────────────────────────────────────┐        │
   │  deflate()      citations → opaque tokens [[c_4]]     │        │
   │       ▼                                               │        │
   │  WriterProvider ── LLM call #2 ───────────────────────┼────────┘
   │       │   sees:   ONE paragraph, tokens only          │
   │       │   knows:  nothing about the document,         │
   │       │           the library, or the plan            │
   │       ▼                                               │
   │  inflate()      original citation objects put back    │
   │       │         where the tokens landed               │
   │       ▼                                               │
   │  GUARD 1  tokens in == tokens out?  else REFUSE       │
   │  GUARD 2  ref_id counts obey this operation's rule?   │
   └──────────────────────────────────────────────────────┘
      │
      ▼
   RevisionProposal        before/after per block. NOTHING WRITTEN.
      │
      ▼
   user ticks the changes they want
      │
      ▼
   apply()  re-verifies against disk:
             1. base revision still current?
             2. each block still holds exactly what the patch assumed?
             3. counts still obey the rule?
      │
      ▼
   rev_N+1.json            rev_N untouched
```

**Two narrow LLM calls, never one big prompt.** The planner picks targets and
writes no prose. The writer sees one paragraph and knows nothing else. Neither
is in a position to do the other's damage.

### The rules each operation must obey

| Operation | Allowed effect on citation counts |
|---|---|
| `shorten_block` | **identical** - nothing added or removed |
| `rewrite_block` | **identical** |
| `add_citation` | may only **increase**, and only from the library |
| `delete_block` | may decrease, but every lost reference is **named** in the preview |

An operation with no declared rule is refused rather than defaulted. "May this
silently drop citations?" is not a question anyone gets to leave blank.

### How peer review works

Three passes, deliberately independent, each needing more of the outside world
than the last:

```
   Document
      │
      │  SentenceProvider     sentences derived IN CODE, with character
      │                       offsets and the citations that fall inside them
      ▼
   Sentence[]
      │
      ├──► PASS A  ClaimProvider    which sentences state a fact but cite nothing?
      │              answers with INDEXES into a batch, never with text
      │
      ├──► PASS C  SupportProvider  does the cited abstract support this claim?
      │              returns QUOTE + GRADE together
      │                    │
      │                    ▼
      │              quote_is_verbatim()  ← checked in PYTHON, not trusted
      │                    │
      │              fails → grade forced to "insufficient_evidence"
      │
      └──► DISCOVERY  search OpenAlex / S2 for works a claim should cite
                     candidates come from the DATABASE; the model only filters
      │
      ▼
   Finding[]  ── final gate: is_grounded ──► anything without a verified quote
                                              or a real source id is DISCARDED
```

**Sentences are derived in code, not chosen by the model.** That is why every
finding carries a real block id, sentence index and character span - a finding
can always be traced back to text that actually exists.

### How the databases are called

```
   Reference
      │
      ├─ has a DOI? ──yes──► find_by_doi()          exact, done
      │
      └─ no ──► search(title)
                   │
                   ├─ OpenAlex        primary, free, no key
                   └─ Semantic Scholar fallback when OpenAlex finds nothing
                                       or is out of quota
                   │
                   ▼
              MatcherProvider  title 0.60 + authors 0.25 + year 0.15
                               ≥ 0.82 accept · ≥ 0.55 ambiguous · else unresolved
                               must beat runner-up by 0.04
                               collapse preprint + published duplicates
                   │
                   ▼
              abstract missing? ──► Semantic Scholar backfill
```

Bounded concurrency (3 at a time), a disk cache keyed on the request, and a
75-second budget on the whole step. Every response is cached, so re-running
costs nothing and a demo is repeatable.

### How citations survive, in one line

The model is handed prose with the citations replaced by tokens it cannot read,
and code puts the real citation objects back where those tokens ended up - so
an edit that damages a citation is not something we detect and fix, it is
something the pipeline cannot express.

---

## Where to read next

| Document | For |
|---|---|
| [connection.md](design/connection.md) | how the parts fit together, with more technical detail |
| [api-design.md](api-design.md) | every endpoint, what it does, and its JSON |
| [extraction.md](design/extraction.md) | how a PDF becomes a structured document |
| [verification.md](design/verification.md) | how references are matched to real works |
| [review.md](design/review.md) | how the AI review works and why it can be trusted |
| [edit.md](design/edit.md) | the citation-safety mechanism in full |
| [export.md](design/export.md) | LaTeX and citation formatting |
