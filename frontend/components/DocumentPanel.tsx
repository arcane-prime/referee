"use client";

import { BlockView } from "@/components/InlineNodes";
import {
  CurrentDocument,
  ExtractionResult,
  ResolvedReference,
} from "@/lib/api";

const VERIFY_LABEL: Record<string, string> = {
  resolved: "found",
  ambiguous: "uncertain",
  unresolved: "not found",
};

function referenceQuality(reference: ResolvedReference): "good" | "failed" {
  return reference.parsed?.title ? "good" : "failed";
}

export default function DocumentPanel({
  extraction,
  current,
  targetedBlocks,
}: {
  extraction: ExtractionResult;
  current: CurrentDocument;
  targetedBlocks: string[];
}) {
  const { references, summary, verification } = extraction;
  const document = current.document;
  const unparsed = references.filter(
    (reference) => referenceQuality(reference) === "failed",
  );
  const targeted = new Set(targetedBlocks);

  return (
    <section className="stack">
      <div className="panel">
        <div className="panel__heading">
          <p className="panel__title">{document.title}</p>
          <RevisionBadge current={current} />
        </div>
        <p className="hint">{document.authors.join(" · ")}</p>

        <div className="stats">
          <Stat label="Sections" value={summary.section_count} />
          <Stat label="Blocks" value={summary.block_count} />
          <Stat label="Citations" value={summary.citation_count} />
          <Stat
            label="Unlinked"
            value={summary.unlinked_citation_count}
            warn={summary.unlinked_citation_count > 0}
          />
          <Stat label="References" value={summary.references.total} />
          <Stat
            label="Unparsed refs"
            value={summary.references.failed}
            warn={summary.references.failed > 0}
          />
        </div>

        <p className="hint">
          Detected style: <strong>{summary.detected_style}</strong>{" "}
          {summary.detected_style === "unknown"
            ? "— pick one manually before exporting."
            : `(confidence ${summary.style_confidence})`}
        </p>
      </div>

      <VerificationBanner extraction={extraction} />

      {targeted.size > 0 && (
        <div className="panel panel--targeted">
          <p className="panel__title">
            {targeted.size} paragraph(s) would change
          </p>
          <p className="hint">
            Highlighted below. Nothing has been written yet — approve the
            changes on the right to create revision {current.revision + 1}.
          </p>
        </div>
      )}

      {verification.succeeded && (
        <div className="panel">
          <p className="panel__title">Every reference, and what we found</p>
          <ul className="refs">
            {references.map((reference) => (
              <li key={reference.id} className="refs__item">
                <span className={`tag tag--${reference.resolution.status}`}>
                  {VERIFY_LABEL[reference.resolution.status]}
                </span>
                <div className="refs__body">
                  <p className="refs__title">
                    {reference.resolution.matched?.title ??
                      reference.parsed?.title ??
                      reference.raw}
                  </p>
                  <p className="refs__meta">
                    <code>{reference.id}</code>
                    {reference.resolution.external_ids.doi && (
                      <>
                        {" · "}
                        <a
                          href={`https://doi.org/${reference.resolution.external_ids.doi}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {reference.resolution.external_ids.doi}
                        </a>
                      </>
                    )}
                    {reference.resolution.abstract && " · abstract available"}
                  </p>
                  {reference.resolution.status !== "resolved" &&
                    reference.resolution.reason && (
                      <p className="refs__reason">{reference.resolution.reason}</p>
                    )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {unparsed.length > 0 && (
        <div className="panel panel--warn">
          <p className="panel__title">
            {unparsed.length} reference(s) could not be parsed
          </p>
          <p className="hint">
            Kept verbatim rather than dropped. They can still be searched as
            plain strings.
          </p>
          <ul className="raw-list">
            {unparsed.map((reference) => (
              <li key={reference.id}>
                <code>{reference.id}</code> {reference.raw}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <p className="panel__title">Parsed document</p>
        <p className="hint">
          Citations are separate nodes, not text. Each chip below is a link to a
          reference — the markers never exist inside the editable prose.
        </p>
        {document.sections.map((section) => (
          <div key={section.id} className="section">
            <h3 className={`section__title section__title--l${section.level}`}>
              {section.title}
            </h3>
            {section.blocks.map((block) => (
              <BlockView
                key={block.id}
                block={block}
                targeted={targeted.has(block.id)}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function RevisionBadge({ current }: { current: CurrentDocument }) {
  const edited = current.revision > 0;

  return (
    <span
      className={`revision${edited ? " revision--edited" : ""}`}
      title={
        edited
          ? `Revision ${current.revision}. Revisions ${current.available_revisions.join(
              ", ",
            )} are all still on disk.`
          : "The original parse. No edits applied."
      }
    >
      rev {current.revision}
      {edited && ` of ${current.available_revisions.length - 1}`}
    </span>
  );
}

function VerificationBanner({ extraction }: { extraction: ExtractionResult }) {
  const { verification } = extraction;

  if (!verification.attempted) return null;

  if (!verification.succeeded) {
    return (
      <div className="panel panel--warn">
        <p className="panel__title">Extracted, but references not verified</p>
        <p className="hint">{verification.message}</p>
        <p className="hint">
          The parse above is complete. Claims cannot be checked against their
          sources, and the agent may not add citations, until the databases are
          reachable again.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <p className="panel__title">
        References checked against {verification.search_api}
      </p>
      <div className="stats">
        <Stat label="Found" value={verification.resolved} />
        <Stat
          label="Uncertain"
          value={verification.ambiguous}
          warn={verification.ambiguous > 0}
        />
        <Stat
          label="Not found"
          value={verification.unresolved}
          warn={verification.unresolved > 0}
        />
        <Stat label="With abstract" value={verification.with_abstract} />
        <Stat label="With DOI" value={verification.with_doi} />
      </div>
      {verification.with_abstract < extraction.summary.references.total && (
        <p className="hint">
          {extraction.summary.references.total - verification.with_abstract}{" "}
          reference(s) have no abstract, so their claims cannot be checked and
          will be skipped.
        </p>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  warn,
}: {
  label: string;
  value: number;
  warn?: boolean;
}) {
  return (
    <div className={`stat${warn ? " stat--warn" : ""}`}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}

/*
 Notes

 This pane renders the manuscript at whatever revision is current, which is why
 it takes `current` separately from `extraction`. The extraction result is a
 fact about the parse and never changes; the document is what edits rewrite.
 Conflating them would mean re-running extraction to see an edit, which would
 call GROBID and the literature databases to rebuild something already on disk.

 The revision badge is small but it is the visible proof of the append-only
 history. rev 0 is the original parse and every approved edit adds one, with
 every earlier revision still on disk, so "undo" is reading a smaller number
 rather than an operation that has to be correct.

 Blocks a pending proposal would touch are highlighted here rather than only
 listed in the diff. The researcher can see which paragraphs of their own paper
 an instruction actually selected before approving anything, which is the
 cheapest possible check on a planner that chose the wrong targets.

 The verification banner also states that the agent may not add citations when
 the databases were unreachable. That is not a UI nicety: with no library there
 is nothing carrying an external id, so check_citable refuses every insertion.
 Saying so up front is better than a refusal the user did not expect.
*/
