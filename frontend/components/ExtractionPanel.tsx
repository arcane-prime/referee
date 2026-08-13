"use client";

import { useCallback, useState } from "react";
import {
  Block,
  ExtractionResult,
  Inline,
  ResolvedReference,
  UploadedPaper,
  extractPaper,
} from "@/lib/api";

const VERIFY_LABEL: Record<string, string> = {
  resolved: "found",
  ambiguous: "uncertain",
  unresolved: "not found",
};

type Status =
  | { phase: "idle" }
  | { phase: "extracting" }
  | { phase: "done"; result: ExtractionResult }
  | { phase: "error"; message: string };

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function referenceQuality(reference: ResolvedReference): "good" | "failed" {
  return reference.parsed?.title ? "good" : "failed";
}

function InlineNode({ node }: { node: Inline }) {
  switch (node.kind) {
    case "text":
      return <>{node.text}</>;
    case "cite":
      return (
        <span
          className={`chip chip--cite${node.ref_ids.length === 0 ? " chip--unlinked" : ""}`}
          title={
            node.ref_ids.length
              ? `${node.raw_marker ?? ""} → ${node.ref_ids.join(", ")}`
              : `${node.raw_marker ?? ""} → not linked to any reference`
          }
        >
          {node.ref_ids.length ? node.ref_ids.join(", ") : "unlinked"}
        </span>
      );
    case "xref":
      return <span className="chip chip--xref">{node.label}</span>;
    case "math":
      return <span className="chip chip--math">{node.source}</span>;
  }
}

function BlockView({ block }: { block: Block }) {
  return (
    <p className={`block block--${block.kind}`}>
      <span className="block__id">{block.id}</span>
      {block.label && <span className="block__label">{block.label}</span>}
      {block.inlines.map((node, index) => (
        <InlineNode key={`${block.id}-${index}`} node={node} />
      ))}
    </p>
  );
}

export default function ExtractionPanel({
  paper,
  onExtracted,
}: {
  paper: UploadedPaper;
  onExtracted: (result: ExtractionResult | null) => void;
}) {
  const [status, setStatus] = useState<Status>({ phase: "idle" });

  const runExtract = useCallback(async () => {
    setStatus({ phase: "extracting" });
    onExtracted(null);
    try {
      const result = await extractPaper(paper.paper_id);
      setStatus({ phase: "done", result });
      onExtracted(result);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Something went wrong.";
      setStatus({ phase: "error", message });
    }
  }, [paper.paper_id, onExtracted]);

  return (
    <section className="stack">
      <div className="panel">
        <p className="panel__title">1 · {paper.filename}</p>
        <dl className="meta">
          <div>
            <dt>Paper ID</dt>
            <dd>
              <code>{paper.paper_id}</code>
            </dd>
          </div>
          <div>
            <dt>Size</dt>
            <dd>{formatBytes(paper.size_bytes)}</dd>
          </div>
        </dl>
        <button
          className="button"
          onClick={() => void runExtract()}
          disabled={status.phase === "extracting"}
        >
          {status.phase === "extracting" ? "Extracting…" : "Extract"}
        </button>
        {status.phase === "extracting" && (
          <p className="hint">
            Parsing the PDF, then checking its references against the literature
            databases. This usually takes 30–60 seconds.
          </p>
        )}
      </div>

      {status.phase === "error" && (
        <div className="panel panel--error">
          <p className="panel__title">Extraction failed</p>
          <p>{status.message}</p>
        </div>
      )}

      {status.phase === "done" && <Result result={status.result} />}
    </section>
  );
}

function Result({ result }: { result: ExtractionResult }) {
  const { document, references, summary, verification } = result;
  const unparsed = references.filter((reference) => referenceQuality(reference) === "failed");

  return (
    <>
      <div className="panel">
        <p className="panel__title">{document.title}</p>
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

      <VerificationBanner result={result} />

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
          <p className="panel__title">{unparsed.length} reference(s) could not be parsed</p>
          <p className="hint">
            Kept verbatim rather than dropped. They can still be searched as plain strings.
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
          Citations are separate nodes, not text. Each chip below is a link to a reference —
          the markers never exist inside the editable prose.
        </p>
        {document.sections.map((section) => (
          <div key={section.id} className="section">
            <h3 className={`section__title section__title--l${section.level}`}>
              {section.title}
            </h3>
            {section.blocks.map((block) => (
              <BlockView key={block.id} block={block} />
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
              <div className="ref-list__raw">{reference.parsed?.title ?? reference.raw}</div>
            </li>
          ))}
        </ol>
      </div>
    </>
  );
}

function VerificationBanner({ result }: { result: ExtractionResult }) {
  const { verification } = result;

  if (!verification.attempted) return null;

  if (!verification.succeeded) {
    return (
      <div className="panel panel--warn">
        <p className="panel__title">Extracted, but references not verified</p>
        <p className="hint">{verification.message}</p>
        <p className="hint">
          The parse above is complete. Claims cannot be checked against their
          sources until the databases are reachable again.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <p className="panel__title">References checked against {verification.search_api}</p>
      <div className="stats">
        <Stat label="Found" value={verification.resolved} />
        <Stat label="Uncertain" value={verification.ambiguous} warn={verification.ambiguous > 0} />
        <Stat label="Not found" value={verification.unresolved} warn={verification.unresolved > 0} />
        <Stat label="With abstract" value={verification.with_abstract} />
        <Stat label="With DOI" value={verification.with_doi} />
      </div>
      {verification.with_abstract < result.summary.references.total && (
        <p className="hint">
          {result.summary.references.total - verification.with_abstract} reference(s)
          have no abstract, so their claims cannot be checked and will be skipped.
        </p>
      )}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={`stat${warn ? " stat--warn" : ""}`}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}

/*
 Notes

 Extraction fires only from the Extract button. Uploading a file does not
 trigger it, so re-parsing after a parser change costs one click rather than a
 re-upload.

 The document renderer switches on the same `kind` discriminator the backend
 wrote, which is what makes the core design decision visible in the UI: a
 citation is drawn as a chip carrying reference ids, and the marker text never
 appears inside the surrounding prose. The chip is generated from the node at
 render time, exactly as citeproc will generate "[12]" at export time.

 Unlinked citations and unparsed references are shown rather than hidden. A
 visible gap is worth more than a silently dropped citation, and both counts
 are surfaced as warnings rather than buried.

 referenceQuality mirrors the server's derived property instead of reading a
 stored field, because the server does not store one. It returns only good or
 failed: the finer good/degraded split the summary counts carry cannot be
 rebuilt from the fields this endpoint returns, so claiming a third case here
 would be a type that lies.

 "unparsed" and "unresolved" are different failures and are named differently
 on purpose. Unparsed means GROBID could not read the reference string at all.
 Unresolved means it parsed cleanly but no matching work was found in the
 literature databases. A reference is routinely one without being the other.
*/
