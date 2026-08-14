"use client";

import { useCallback, useState } from "react";
import {
  Evidence,
  Finding,
  ReviewResult,
  SupportGrade,
  reviewPaper,
} from "@/lib/api";

type Status =
  | { phase: "idle" }
  | { phase: "reviewing" }
  | { phase: "done"; result: ReviewResult }
  | { phase: "error"; message: string };

const GRADE_LABEL: Record<SupportGrade, string> = {
  supports: "supports",
  partially_supports: "only partly supports",
  not_supported: "contradicts",
  insufficient_evidence: "does not address",
};

const KIND_LABEL: Record<Finding["kind"], string> = {
  unsupported_claim: "claim vs source",
  missing_citation: "missing citation",
  uncited_claim: "no citation",
};

export default function ReviewPanel({
  paperId,
  verified,
}: {
  paperId: string;
  verified: boolean;
}) {
  const [status, setStatus] = useState<Status>({ phase: "idle" });

  const run = useCallback(async () => {
    setStatus({ phase: "reviewing" });
    try {
      const result = await reviewPaper(paperId, verified);
      setStatus({ phase: "done", result });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Something went wrong.";
      setStatus({ phase: "error", message });
    }
  }, [paperId, verified]);

  return (
    <section className="stack">
      <div className="panel">
        <p className="panel__title">2 · Review with AI</p>
        <p className="hint">
          {verified
            ? "Checks each cited claim against the abstract of the work it cites, quotes the evidence it judged from, and flags claims that carry no citation."
            : "References were not verified, so claims cannot be checked against their sources. The review will flag claims that carry no citation."}
        </p>


        <button
          className="button"
          onClick={() => void run()}
          disabled={status.phase === "reviewing"}
        >
          {status.phase === "reviewing" ? "Reviewing…" : "Get suggestions"}
        </button>
        {status.phase === "reviewing" && (
          <p className="hint">Reading the paper and judging its claims…</p>
        )}
      </div>

      {status.phase === "error" && (
        <div className="panel panel--error">
          <p className="panel__title">Review failed</p>
          <p>{status.message}</p>
        </div>
      )}

      {status.phase === "done" && <ReviewReport result={status.result} />}
    </section>
  );
}

function ReviewReport({ result }: { result: ReviewResult }) {
  const { findings, summary } = result;

  return (
    <>
      <div className="panel">
        <p className="panel__title">What the review examined</p>
        <div className="stats">
          <Stat label="Sentences" value={summary.sentences_examined} />
          <Stat label="Cited claims" value={summary.claims_with_citations} />
          <Stat label="Citations checked" value={summary.citations_checked} />
          <Stat
            label="Skipped, no abstract"
            value={summary.references_without_abstract}
            warn={summary.references_without_abstract > 0}
          />
          <Stat label="Findings" value={summary.findings_total} warn={summary.findings_total > 0} />
        </div>
        <p className="hint">Judged by {result.model}.</p>
      </div>

      {findings.length === 0 ? (
        <div className="panel">
          <p className="panel__title">Nothing flagged</p>
          <p className="hint">
            Every claim the review could check looked properly supported.
            {summary.references_without_abstract > 0 &&
              " References with no abstract were skipped rather than guessed at."}
          </p>
        </div>
      ) : (
        findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)
      )}
    </>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <div className={`panel finding finding--${finding.severity}`}>
      <div className="finding__head">
        <span className={`tag tag--${finding.kind}`}>{KIND_LABEL[finding.kind]}</span>
        <code className="finding__anchor">
          {finding.block_id} · sentence {finding.sentence_index}
        </code>
      </div>

      <p className="finding__sentence">{finding.sentence}</p>
      <p className="finding__message">{finding.message}</p>

      {finding.evidence.map((item, index) => (
        <EvidenceCard key={`${finding.id}-${index}`} evidence={item} />
      ))}

      {finding.suggested_sources.length > 0 && (
        <ul className="sources">
          {finding.suggested_sources.map((source, index) => (
            <li key={`${finding.id}-s${index}`}>
              <a href={source.url ?? "#"} target="_blank" rel="noreferrer">
                {source.title}
              </a>
              {source.year && <span className="sources__year"> ({source.year})</span>}
              {source.reason && <p className="sources__reason">{source.reason}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EvidenceCard({ evidence }: { evidence: Evidence }) {
  return (
    <div className="evidence">
      <p className="evidence__head">
        {evidence.source_title ?? evidence.ref_id}{" "}
        <span className={`grade grade--${evidence.grade}`}>
          {GRADE_LABEL[evidence.grade]}
        </span>
      </p>

      {evidence.quote && evidence.quote_verified ? (
        <blockquote className="evidence__quote">“{evidence.quote}”</blockquote>
      ) : (
        <p className="evidence__none">
          No verified quote from the abstract, so this was not treated as evidence.
        </p>
      )}

      {evidence.note && <p className="evidence__note">{evidence.note}</p>}

      {evidence.source_url && (
        <a
          className="evidence__link"
          href={evidence.source_url}
          target="_blank"
          rel="noreferrer"
        >
          Open the source
        </a>
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
