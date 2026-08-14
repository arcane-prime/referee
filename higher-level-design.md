# High-level design

**Diagram:** https://excalidraw.com/#json=C64ZG4E43_vYbprMB0VO6,ysppSaCXiyz4yZfaq4DhZA

*(the board holds two diagrams — the first is from an earlier interview, the
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

**The browser** — the researcher's screen. One page, split into two: the paper
on the left, the AI on the right.

**The Referee API** — a Python server holding all the logic. It talks to four
outside services and stores everything as plain files.

**File storage** — one folder per paper. No database. A paper is a small amount
of data used by one person, so a database would be machinery bought for a
problem this does not have.

**Four outside services**

| | What it is for |
|---|---|
| **GROBID** | turns a PDF into structured XML. Runs in Docker, or use a free public one |
| **OpenAlex** | a free database of academic papers — the main reference lookup |
| **Semantic Scholar** | a second database, used as backup and for abstracts |
| **OpenAI** | the language model that reviews and rewrites |

Nothing in the code names a vendor except one wiring file. Swapping the language
model provider, or the PDF parser, means writing one new file.

---

## How a paper moves through it

**1. Upload.** The PDF is saved and never touched again. Whatever happens next,
the researcher's original file is always there to download.

**2. Parse** *(under a second)*. GROBID converts the PDF to XML; the app turns
that into its own document format — sections, paragraphs, citations. Saved as
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

as exactly that — one string. Referee stores it as a *list of pieces*:

```
a piece of text:   "Transformers dominate NLP "
a citation:        points at reference 12
a piece of text:   ". Recent work extends this to vision "
a citation:        points at references 13 and 14
a piece of text:   "."
```

The characters `[12]` are stored **nowhere**. A citation is an object that
points at a bibliography entry. The `[12]` a reader sees is printed at the last
moment — by the screen when displaying, and by the citation formatter when
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
*what* the citation is — it never saw a reference id, a title, or an author.

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
  reference merely read off the user's own PDF is not enough — it has to have
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
database, it stays — even if the edit that discovered it was rejected. Otherwise
an older version of the paper could end up pointing at a reference that had
disappeared.

---

## When something breaks

Every outside service can fail without taking the app down.

| If this is unavailable | You lose | You keep |
|---|---|---|
| GROBID | uploading a **new** paper | everything else — review, edit, export |
| OpenAlex | — | Semantic Scholar picks up the search |
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
- references whose text the parser could not understand — kept and shown
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
absent from the databases — a 1967 Soviet journal, a paper published too
recently to be indexed, and a poorly indexed one from 2009.

That number is reported as it is. A tool that quietly showed 38 of 38 would be
easier to demo and worth much less.

---

## Where to read next

| Document | For |
|---|---|
| [connection.md](connection.md) | how the parts fit together, with more technical detail |
| [api.md](api.md) | every endpoint, what it does, and its JSON |
| [extraction.md](extraction.md) | how a PDF becomes a structured document |
| [verification.md](verification.md) | how references are matched to real works |
| [review.md](review.md) | how the AI review works and why it can be trusted |
| [edit.md](edit.md) | the citation-safety mechanism in full |
| [export.md](export.md) | LaTeX and citation formatting |
