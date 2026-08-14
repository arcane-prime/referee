# API design

**Base URL:** `http://localhost:8000`
**Live docs:** `http://localhost:8000/docs`

Eleven endpoints, grouped by the module that owns them. Part 1 lists what each
one does. Part 2 shows the JSON that goes in and comes back.

---

# Part 1 — What each module offers

## Module: `papers` — getting a paper into the system

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/papers` | Upload a PDF. Returns a `paper_id` used by every other call. |

The upload is checked before it is stored: the file must really be a PDF (it has
to start with the bytes `%PDF-`) and must be under 50 MB. A file merely *named*
`.pdf` is rejected here rather than confusing the parser later.

---

## Module: `extraction` — turning the PDF into a document

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/papers/{id}/extract` | Parse the PDF into sections, paragraphs and citations. |
| `GET` | `/parser/status` | Is the PDF parser (GROBID) running? |

**`/extract`** is fast — under a second. It sends the PDF to GROBID, converts
the result into our own document format, and saves it as revision 0.

It does **not** check any references against the internet. That is a separate
call, because it is roughly fifty times slower.

Optional: `?use_cached_tei=true` re-runs the conversion on parser output already
saved on disk, without calling GROBID again. Useful while developing.

---

## Module: `resolution` — checking the references are real

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/papers/{id}/resolve` | Look up every reference in OpenAlex and Semantic Scholar. |

For each reference in the bibliography this finds the real published work,
its DOI, and its abstract. Roughly 30 seconds for 40 references, because each
one is a lookup against a free public database.

Every reference comes back as one of three things, and the difference matters:

- **resolved** — we are confident this is the work, here is its DOI
- **ambiguous** — plausible matches, none convincing enough
- **unresolved** — nothing credible found, and we say so

The whole call is capped at 75 seconds. If the databases are throttling us it
gives up and says so rather than hanging, and the parsed paper is unaffected.

---

## Module: `review` — the AI peer review

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/papers/{id}/review` | Review the paper and return findings. |

Produces reviewer-style findings of three kinds:

- **a claim its cited source does not actually support**
- **a claim with no citation, where we found real works that could support it**
- **a claim with no citation, where we could not search**

Each finding points at an exact sentence, and carries either a quote from the
cited work's abstract or a real linkable source. Takes 15–45 seconds.

Four optional switches:

| Query | Default | Effect |
|---|---|---|
| `revision` | latest | which version of the paper to review |
| `check_support` | `true` | check claims against the abstracts they cite |
| `find_uncited_claims` | `true` | find claims carrying no citation |
| `find_missing_work` | `true` | search the literature for works it should cite |

The switches exist so the review still works when something is unavailable. With
no search quota left, turning off `find_missing_work` still gives a complete and
honest review of everything else.

---

## Module: `editing` — changing the paper with plain English

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/papers/{id}/edit/plan` | Turn an instruction into proposed changes. **Saves nothing.** |
| `POST` | `/papers/{id}/edit/apply` | Approve some or all of those changes. Saves a new version. |
| `GET` | `/papers/{id}/document` | Read the paper at its latest version, or any earlier one. |

**`/edit/plan`** takes something like *"make the introduction shorter"* and
returns a before/after for each paragraph it would change, plus a note of what
happened to the citations in it. Nothing is written to disk.

It also returns anything it **refused** to do, with the reason. If the AI's
rewrite would have dropped a citation, that paragraph is rejected and named
rather than quietly applied.

**`/edit/apply`** takes the proposal back, plus a list of which paragraphs you
approved, and writes a new version. The old version is never overwritten — the
paper accumulates revision 0, 1, 2 and so on.

**`/document`** lets you read any of those versions back without re-parsing the
PDF.

---

## Module: `export` — getting the paper back out

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/papers/{id}/export` | What can be exported, and in which citation styles. |
| `GET` | `/papers/{id}/export.tex` | Download the paper as a LaTeX file. |

**`/export`** tells a user interface which citation styles are available (APA,
IEEE, Nature) and which one was detected in the original paper, so it can offer
a sensible dropdown.

**`/export.tex`** returns the actual file, not JSON. Optional `?revision=` and
`?style=`. The bibliography is formatted from a real citation stylesheet and
embedded in the file, so it compiles with a single `pdflatex` run.

---

## System

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/health` | Is the server up? |

---

## The order they are called in

```
POST /papers                    →  paper_id
POST /papers/{id}/extract       →  the parsed paper          (fast)
POST /papers/{id}/resolve       →  references verified       (slow)

then, in any order and as often as you like:

POST /papers/{id}/review        →  findings
POST /papers/{id}/edit/plan     →  proposed changes
POST /papers/{id}/edit/apply    →  a new revision
GET  /papers/{id}/export.tex    →  a LaTeX file
```

The first three must happen in that order. Everything after reads what they
wrote, so review, editing and export never re-parse or re-search.

---
---

# Part 2 — Request and response shapes

## Upload a paper

`POST /papers` · form data, field name `file`

**Response — 201**

```json
{
  "paper_id": "paper_9d9b776178a4",
  "filename": "attention.pdf",
  "size_bytes": 2215244,
  "uploaded_at": "2026-08-14T10:12:03Z"
}
```

---

## Parse the paper

`POST /papers/{id}/extract` · no body

**Response — 200**

```json
{
  "paper_id": "paper_9d9b776178a4",
  "parser": "grobid",
  "document": {
    "revision": 0,
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer"],
    "style": "ieee",
    "sections": [
      {
        "id": "s0",
        "title": "Introduction",
        "blocks": [
          {
            "id": "s0.p0",
            "kind": "paragraph",
            "inlines": [
              { "kind": "text", "text": "Recurrent models have long dominated " },
              { "kind": "cite", "id": "c_4", "ref_ids": ["ref_12"], "raw_marker": "[12]" },
              { "kind": "text", "text": " sequence modelling." }
            ]
          }
        ]
      }
    ]
  },
  "references": [
    { "id": "ref_12", "raw": "Vaswani et al. Attention is all you need. 2017." }
  ],
  "summary": {
    "section_count": 28,
    "block_count": 110,
    "citation_count": 58,
    "unlinked_citation_count": 0,
    "references": { "total": 70, "good": 64, "degraded": 4, "failed": 2 },
    "detected_style": "ieee",
    "style_confidence": 0.94
  }
}
```

**The `inlines` list is the important part.** A paragraph is not a sentence of
text — it is a list of pieces. `text` is ordinary prose. `cite` is a citation
pointing at a reference id. There are also `math` and `xref` (figure and table
references).

Notice the characters `[12]` appear nowhere in the prose. They exist only in
`raw_marker`, as a record of what was printed. The visible `[12]` is generated
when the paper is displayed or exported.

`unlinked_citation_count` and `references.failed` are how the response admits
what it could not do, rather than returning fewer citations and staying quiet.

---

## Check the references

`POST /papers/{id}/resolve` · no body

**Response — 200**

```json
{
  "search_api": "openalex+semantic_scholar",
  "abstract_api": "semantic_scholar",
  "references": [
    {
      "id": "ref_12",
      "raw": "Vaswani et al. Attention is all you need. 2017.",
      "resolution": {
        "status": "resolved",
        "score": 0.94,
        "external_ids": { "doi": "10.5555/3295222", "openalex": "W2963403868" },
        "abstract": "The dominant sequence transduction models are based on...",
        "reason": null
      },
      "provenance": "fetched_from_api"
    },
    {
      "id": "ref_31",
      "raw": "R. Adam, Sobolev Spaces, Academic Press, 1975.",
      "resolution": {
        "status": "unresolved",
        "score": 0.0,
        "external_ids": { "doi": null },
        "abstract": null,
        "reason": "Best candidate scored 0.00, below the 0.55 threshold."
      },
      "provenance": "parsed_from_pdf"
    }
  ],
  "summary": {
    "total": 38, "resolved": 31, "ambiguous": 1, "unresolved": 6,
    "with_abstract": 26, "with_doi": 31
  }
}
```

`reason` is written in plain English because it is shown to the user.

`provenance` matters more than it looks: `fetched_from_api` means a real
database returned this record. The AI is only ever allowed to add a citation
pointing at one of those, which is what makes an invented reference impossible.

`with_abstract` is counted separately from `resolved` because it is the number
the review depends on — a reference can be correctly identified and still have
no abstract to check claims against.

---

## Review the paper

`POST /papers/{id}/review` · no body

**Response — 200**

```json
{
  "revision": 2,
  "model": "openai",
  "findings": [
    {
      "id": "f_0001",
      "kind": "unsupported_claim",
      "severity": "medium",
      "block_id": "s0.p2",
      "sentence_index": 1,
      "start": 142,
      "end": 268,
      "sentence": "Transformers outperform recurrent models on all sequence tasks.",
      "message": "The cited source only partially supports this claim.",
      "evidence": [
        {
          "ref_id": "ref_12",
          "grade": "partially_supports",
          "quote": "we show it is superior in quality on two machine translation tasks",
          "quote_verified": true,
          "source_title": "Attention Is All You Need",
          "source_url": "https://doi.org/10.5555/3295222"
        }
      ],
      "suggested_sources": []
    }
  ],
  "summary": {
    "sentences_examined": 335,
    "claims_with_citations": 46,
    "citations_checked": 51,
    "references_without_abstract": 12,
    "findings_total": 20,
    "unsupported_claims": 6,
    "missing_citations": 2
  }
}
```

`kind` is one of `unsupported_claim`, `missing_citation`, `uncited_claim`.
`grade` is one of `supports`, `partially_supports`, `not_supported`,
`insufficient_evidence`.

`block_id`, `sentence_index`, `start` and `end` let a user interface point at
the exact sentence in the paper. The AI picks *which* sentence; it never writes
the sentence text, so a finding can always be traced back.

**`quote_verified` is checked in code, not claimed by the model.** After the AI
returns a quote, the server checks that the quote really appears in the
abstract. If it does not, the verdict is thrown away and downgraded. That is why
a finding can be trusted.

`revision` says which version of the paper was reviewed — without it, findings
about a paragraph a later edit removed would look like nonsense.

---

## Propose an edit

`POST /papers/{id}/edit/plan`

**Request**

```json
{ "command": "make the introduction shorter" }
```

Maximum 500 characters — it is an instruction, not a document.

**Response — 200**

```json
{
  "applicable": true,
  "message": "6 change(s) ready for review.",
  "proposal": {
    "paper_id": "paper_9d9b776178a4",
    "base_revision": 1,
    "intent": "shorten the introduction",
    "patches": [
      {
        "block_id": "s0.p3",
        "operation": "shorten_block",
        "before": [
          { "kind": "text", "text": "Recurrent models have long dominated " },
          { "kind": "cite", "id": "c_4", "ref_ids": ["ref_12"] },
          { "kind": "text", "text": " sequence modelling, and remain widely used." }
        ],
        "after": [
          { "kind": "text", "text": "Recurrent models dominated sequence modelling " },
          { "kind": "cite", "id": "c_4", "ref_ids": ["ref_12"] },
          { "kind": "text", "text": "." }
        ],
        "citations": { "added": [], "removed": [], "moved": ["c_4"] },
        "deleted": false
      }
    ],
    "rejected": [
      {
        "block_id": "s0.p6",
        "operation": "shorten_block",
        "reason": "The rewrite invented 3 marker(s) that were not in the original text: c_4, m_1, x_2."
      }
    ],
    "citations": { "added": [], "removed": [], "moved": ["c_4"] }
  }
}
```

`before` and `after` are the same list-of-pieces shape as the document, not
plain strings. That is what lets a user interface draw the citation in the diff
using exactly the same code that drew it in the paper.

**`citations` splits `moved` from `added` and `removed` deliberately.** A
citation shifting position during a shorten is normal and expected. One
appearing or disappearing is a decision the user has to see.

**A refusal is still a successful response.** "What would this command do?" was
answered; the answer is that part of it cannot be done safely. `rejected` names
the paragraph and the reason, and the changes that did work are still offered.

`operation` is one of `shorten_block`, `rewrite_block`, `add_citation`,
`delete_block`.

---

## Apply an edit

`POST /papers/{id}/edit/apply`

**Request** — send the proposal back exactly as received, plus which paragraphs
you approved:

```json
{
  "proposal": { "...the whole object from /edit/plan..." },
  "approved": ["s0.p3", "s0.p4"]
}
```

Leaving out `approved` means all of them.

**Response — 200**

```json
{
  "applied": {
    "revision": 2,
    "base_revision": 1,
    "command": "make the introduction shorter",
    "applied_blocks": ["s0.p3", "s0.p4"],
    "citations": { "added": [], "removed": [], "moved": ["c_4"] }
  },
  "message": "Applied 2 change(s) as revision 2. Revision 1 is unchanged on disk."
}
```

Sending the whole proposal back keeps the server stateless — a proposal cannot
expire because a process restarted. But it also means that by the time it
arrives it is untrusted input, so before writing anything the server re-checks:

1. the paper is still at the revision the proposal was built against
2. each targeted paragraph still contains exactly what the proposal says it did
3. the citation counts still obey that operation's rule

A tampered `after` list that quietly dropped a citation fails check 3.

---

## Read the paper

`GET /papers/{id}/document?revision=2`

**Response — 200**

```json
{
  "paper_id": "paper_9d9b776178a4",
  "revision": 2,
  "available_revisions": [0, 1, 2],
  "document": { "...same shape as in /extract..." }
}
```

Leave off `revision` to get the latest. `available_revisions` is returned
because the history is a feature — every earlier version is still on disk.

---

## Export

`GET /papers/{id}/export`

```json
{
  "paper_id": "paper_9d9b776178a4",
  "revision": 2,
  "available_revisions": [0, 1, 2],
  "detected_style": "unknown",
  "available_styles": ["apa", "ieee", "nature"]
}
```

`detected_style: "unknown"` is a real answer, not a failure — it means the
original paper's citation style could not be identified confidently, so the user
should pick one.

`GET /papers/{id}/export.tex?revision=2&style=ieee`

Returns the file itself rather than JSON:

```
Content-Type: application/x-tex; charset=utf-8
Content-Disposition: attachment; filename="paper_9d9b776178a4_rev2.tex"
X-Referee-Style: ieee
X-Referee-Revision: 2
X-Referee-Bibliography-Entries: 27
```

The facts a caller still needs go in headers, because they cannot be read out of
a file body. The style is reported explicitly since detection can fail and a
requested style may be one we do not ship.

---

## Status

`GET /parser/status` → `{ "parser": "grobid", "alive": true }`
`GET /health` → `{ "status": "ok" }`

---

## When something goes wrong

Every failure has the same shape:

```json
{
  "code": "search_unavailable",
  "detail": "OpenAlex has exhausted this client's daily quota. It resets in 19.8 hours."
}
```

`code` is stable and meant to be checked by code. `detail` is written for a
person and may change.

| Status | Code | Means |
|---|---|---|
| 400 | `invalid_upload` | not a PDF |
| 404 | `paper_not_found` | no such paper id |
| 409 | `not_extracted` | right request, wrong order — parse it first |
| 409 | `edit_conflict` | the paper changed after the proposal was prepared |
| 413 | `upload_too_large` | over 50 MB |
| 422 | `extraction_failed` | the parser answered, but the file could not be used |
| 422 | `edit_refused` | the edit would have damaged the paper — nothing written |
| 500 | `storage_error` | could not read or write to disk |
| 502 | `parser_unavailable` | GROBID unreachable |
| 502 | `search_unavailable` | the reference databases are down or out of quota |
| 502 | `review_unavailable` | the AI model is unreachable or rate limiting |

Three distinctions that carry real information:

- **502 versus 500** — 502 means the problem is in someone else's service,
  nothing was half-saved, and trying again later is sensible. 500 means it was
  our fault.
- **`parser_unavailable` versus `extraction_failed`** — the first means try
  again. The second means the parser answered fine and the *file* is the
  problem, so retrying the same PDF will not help.
- **409 versus 404** — the paper exists; you asked for a step out of order. The
  fix is a different request, not a corrected id.

---

## Conventions

**No pagination.** One paper's document and references are a few hundred
kilobytes, fetched once per stage. Pagination would be complexity bought for a
problem this data does not have.

**No authentication.** This is a single-user local tool.

**Summaries are computed for each response, never stored.** Every number is
counted from the data being returned, so it cannot drift out of step with it.

**The same objects go over the wire as are used internally.** A `Document`, a
`Reference` and a `Finding` are the same shape in the API as in the code, so
there is one definition of each rather than two that can disagree.
