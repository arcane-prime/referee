# Export - turning the document back into a paper

**Module:** `backend/app/modules/export/`
**Routes:** `GET /papers/{id}/export`, `GET /papers/{id}/export.tex`

---

## What this feature does

Takes any revision of the paper and writes it out as a LaTeX file, with every
citation as a real `\cite{}` command and a bibliography formatted by citeproc
from an official CSL stylesheet.

The `.tex` compiles to a PDF with **one `pdflatex` run** - no BibTeX step,
because the bibliography is embedded in the file.

---

## LaTeX, not PDF - and why

The brief asks for exactly this:

> Show the changes for the user to approve, then export the revised paper. **We
> recommend rebuilding the paper as LaTeX** so the structure, sections, and
> references survive the round trip.

The round trip is **structure-preserving, not pixel-preserving**. You get the
title, authors, sections, prose, formulas and every citation. You do not get the
original two-column layout or the figures - those were never in the parse to
begin with.

---

## Where CSL fits

This is the promise the whole codebase was built around, stated in
`domain/csl.py` from day one:

> CSL-JSON is the one canonical shape for citation data. Everything becomes a
> `CSLItem`: what is scraped out of the user's PDF, and what is fetched from
> OpenAlex later. All printing is done by citeproc from a `.csl` stylesheet.
> There are no string templates for citations anywhere in this codebase.

Until this module existed, the second half of that was aspirational. Now it is
true.

**The proof** - same reference, one data model, three stylesheets:

```
  ieee: [27]A. H. Schatz and L. B. Wahlbin, "Interior Maximum-Norm Estimates…",
        Mathematics of Computation, vol. 64, no. 211, pp. 907–907, 1995.

   apa: Schatz, A. H., & Wahlbin, L. B.. (1995). Interior Maximum-Norm
        Estimates for Finite Element Methods, Part II. Mathematics of…

nature: 27. Schatz, A. H. & Wahlbin, L. B.. Interior Maximum-Norm Estimates
        for Finite Element Methods, Part II. Mathematics of Computation…
```

Nothing in our code knows what an IEEE citation looks like. The `.csl` file does.

---

## The flow

```
revision number + requested style
   ↓  RevisionProvider.load()            the document
   ↓  LibraryProvider.load()             the references
   ↓  resolve_style()                    requested → detected → ieee
   ↓  _cited_ids()                       which references does this revision cite?
   ↓  csl_items()                        Reference → CSL-JSON dicts
   ↓  render()                           citeproc + .csl → formatted strings
   ↓  render_document()                  document + entries → LaTeX
.tex file  →  browser download
```

---

## The files, and what each one does

### `styles/`

Three official CSL stylesheets, committed to the repo: `ieee.csl`, `apa.csl`,
`nature.csl`.

They are committed rather than downloaded at runtime. They change rarely, and an
exporter that needs the network to format a bibliography would fail in exactly
the situation where a user most wants their paper out.

### `provider/bibliography_provider.py`

Everything to do with citations as data.

| Function | What it does |
|---|---|
| `available_styles()` | which `.csl` files ship |
| `style_path()` | style name → file path, falling back to IEEE |
| `resolve_style()` | pick a style: requested → detected → IEEE |
| `csl_items()` | `Reference` objects → CSL-JSON dicts |
| `render()` | CSL-JSON + stylesheet → formatted bibliography strings |
| `_csl_item()` | one `Reference` → one CSL-JSON dict |

**Style selection has three fallbacks in order**: what the caller asked for,
what extraction detected, then IEEE. Detection returns `"unknown"` when the
sample of markers was not convincing, and the brief's instruction in that case
is to let the user pick. IEEE is a last resort, and the response says which
style was actually used.

**`_csl_item()` rewrites `id`** to the reference id rather than trusting what
the `CSLItem` carried. The id is the citation key the `\cite{}` commands use, so
it has to match the document's `ref_ids` exactly.

**A reference whose parse failed still gets an entry**, using its raw string as
the title. Dropping it would leave a `\cite` in the body pointing at nothing -
the one failure the brief explicitly prohibits. Printing the verbatim string is
ugly and honest: the reader sees exactly what was on the page.

**Keys and rendered entries are zipped with `strict=True`.** citeproc returns a
list positionally, so if it ever emitted a different number of entries than it
was given items, a lenient zip would pair every key after that point with the
wrong reference - a bibliography that looks perfect and is wrong. Nothing
downstream could detect that, so raising is the only safe answer.

### `provider/latex_provider.py`

Turning the document into LaTeX. Pure functions, no decisions.

| Function | What it does |
|---|---|
| `escape()` | escape LaTeX special characters in prose |
| `render_inline()` | one inline node → LaTeX |
| `render_block()` | one block → a paragraph, abstract, equation or quote |
| `render_section()` | section title + its blocks |
| `render_document()` | the whole file, preamble to `\end{document}` |
| `render_bibliography()` | the `thebibliography` environment |

**How each node renders:**

| Node | Becomes |
|---|---|
| `TextRun` | escaped prose |
| `CiteNode` | `\cite{ref_12,ref_13}` |
| `MathNode` | `$...$`, passed through unescaped |
| `XRefNode` | its label as plain text |

**Escaping runs over `TextRun` content only.** `MathNode.source` came out of a
`<formula>` element and is already LaTeX - escaping it would turn a formula into
a printed backslash. This is the one place the exporter trusts its input.

The backslash substitution is in the **same pass** as the others. Doing it first
would escape the backslashes introduced by escaping `&` and `%`. Building the
string character by character makes that impossible to get wrong by reordering.

**An unlinked `CiteNode` renders as nothing.** It is a marker the parser found
but could not attach to any reference, so there is no key to cite, and
`\cite{}` would produce a LaTeX error. Those are surfaced in the parse report,
not here.

**`XRefNode` renders as its label, not `\ref{}`.** The label is what the author
wrote and is guaranteed to read correctly; `\ref{}` would need a matching
`\label{}` on a figure this exporter does not emit, and would silently produce
`??` in the compiled PDF.

**The bibliography is a `thebibliography` environment**, not a `.bib` file.
Each `\bibitem{ref_12}` is followed by text citeproc produced from the `.csl`.
That keeps the no-string-templates promise, and means the file compiles on its
own.

### `provider/export_provider.py`

| Function | What it does |
|---|---|
| `latex()` | the whole pipeline; returns source, revision, style, entry count |
| `_cited_ids()` | which reference ids this revision actually cites |

**Export reads and never writes.** It takes a revision that already exists and a
library resolution already produced, so exporting is a pure function of what is
on disk and can be repeated without cost or risk.

**Any revision can be exported**, not just the latest. Revisions are
append-only, so "give me the paper before I accepted that edit" is a parameter
rather than an undo - and a researcher can diff two exports to see exactly what
an instruction changed.

**Only cited references reach the bibliography.** The library is append-only and
accumulates every work the agent ever discovered, including ones from proposals
the user rejected. A bibliography listing works the paper does not cite would be
wrong in a way that is hard to notice.

`_cited_ids()` is derived from `ref_id_counts()` - the same function the edit
invariant uses to prove citations survived. The bibliography and the safety
check read the document through **one definition** of "what does this paper
cite", so they cannot disagree.

---

## The routes

### `GET /papers/{paper_id}/export`

What can be exported: current revision, all available revisions, the detected
style, and which styles ship. The UI needs this to offer a style picker without
guessing.

### `GET /papers/{paper_id}/export.tex`

Query: `?revision=N&style=ieee`

Returns the `.tex` as a file download. Response headers carry the facts the
caller needs but cannot read out of a file body:

```
content-disposition: attachment; filename="paper_1565d341a0ae_rev2.tex"
x-referee-style: ieee
x-referee-revision: 2
x-referee-bibliography-entries: 27
```

The style is returned explicitly because detection can fail and a requested
style can be one we do not ship - "which stylesheet formatted this" is never
assumed to be what was asked for.

---

## Verified on a real paper

```
rev0: 82,025 chars, 43 \cite commands
rev2: 81,310 chars, 43 \cite commands   ← two AI edits later
```

The export independently demonstrates the editing guarantee: the paper got
shorter, and every citation is still there.

---

## Known limits

- LaTeX, not PDF. Compiling is left to the user (`pdflatex` or Overleaf).
- Figures and tables are not emitted - only their captions were parsed.
- In-text citation *numbering* comes from LaTeX; only the bibliography entry
  *formatting* comes from CSL. For an author-year style the body would need
  `natbib` to render `(Smith, 2019)` rather than `[1]`.
