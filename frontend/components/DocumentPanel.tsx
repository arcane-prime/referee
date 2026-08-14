"use client";

import type { ResolveState } from "@/app/page";
import ExportPanel from "@/components/ExportPanel";
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

function countLive(document: CurrentDocument["document"]) {
  let blocks = 0;
  let citations = 0;
  let unlinked = 0;

  for (const section of document.sections) {
    for (const block of section.blocks) {
      blocks += 1;
      for (const node of block.inlines) {
        if (node.kind !== "cite") continue;
        citations += 1;
        if (node.ref_ids.length === 0) unlinked += 1;
      }
    }
  }

  return { sections: document.sections.length, blocks, citations, unlinked };
}

export default function DocumentPanel({
  extraction,
  resolve,
  current,
  targetedBlocks,
}: {
  extraction: ExtractionResult;
  resolve: ResolveState;
  current: CurrentDocument;
  targetedBlocks: string[];
}) {
  const { summary } = extraction;
  const references =
    resolve.phase === "done" ? resolve.result.references : extraction.references;
  const document = current.document;
  const unparsed = references.filter(
    (reference) => referenceQuality(reference) === "failed",
  );
  const targeted = new Set(targetedBlocks);
  const live = countLive(document);

  return (
    <section className="stack">
      <div className="panel">
        <div className="panel__heading">
          <p className="panel__title">{document.title}</p>
          <RevisionBadge current={current} />
        </div>
        <p className="hint">{document.authors.join(" · ")}</p>

        <div className="stats">
          <Stat label="Sections" value={live.sections} />
          <Stat label="Blocks" value={live.blocks} />
          <Stat label="Citations" value={live.citations} />
          <Stat
            label="Unlinked"
            value={live.unlinked}
            warn={live.unlinked > 0}
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

      <VerificationBanner resolve={resolve} total={summary.references.total} />

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

      {resolve.phase === "done" && (
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

      <div className="panel">
        <p className="panel__title">References ({references.length})</p>
        <ol className="ref-list">
          {references.map((reference) => (
            <li key={reference.id}>
              <code>{reference.id}</code>
              <span className={`badge badge--${referenceQuality(reference)}`}>
                {referenceQuality(reference)}
              </span>
              <div className="ref-list__raw">
                {reference.parsed?.title ?? reference.raw}
              </div>
            </li>
          ))}
        </ol>
      </div>

      <ExportPanel paperId={current.paper_id} revision={current.revision} />

      <div className="pane__end" aria-hidden="true" />
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

function VerificationBanner({
  resolve,
  total,
}: {
  resolve: ResolveState;
  total: number;
}) {
  if (resolve.phase === "idle") return null;

  if (resolve.phase === "checking") {
    return (
      <div className="panel panel--pending">
        <p className="panel__title">Checking references against the literature…</p>
        <p className="hint">
          Looking up {total} reference(s) on OpenAlex, falling back to Semantic
          Scholar for anything it cannot find. The parse below is already
          complete and does not depend on this.
        </p>
        <div className="progress" aria-hidden="true">
          <span className="progress__bar" />
        </div>
      </div>
    );
  }

  if (resolve.phase === "failed") {
    return (
      <div className="panel panel--warn">
        <p className="panel__title">References not verified</p>
        <p className="hint">{resolve.message}</p>
        <p className="hint">
          The parse below is complete and unaffected. Claims cannot be checked
          against their sources, and the agent may not add citations, until the
          databases are reachable again.
        </p>
      </div>
    );
  }

  const { summary, search_api } = resolve.result;

  return (
    <div className="panel">
      <p className="panel__title">References checked against {search_api}</p>
      <div className="stats">
        <Stat label="Found" value={summary.resolved} />
        <Stat label="Uncertain" value={summary.ambiguous} warn={summary.ambiguous > 0} />
        <Stat
          label="Not found"
          value={summary.unresolved}
          warn={summary.unresolved > 0}
        />
        <Stat label="With abstract" value={summary.with_abstract} />
        <Stat label="With DOI" value={summary.with_doi} />
      </div>
      {summary.with_abstract < summary.total && (
        <p className="hint">
          {summary.total - summary.with_abstract} reference(s) have no abstract,
          so their claims cannot be checked and will be skipped.
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
