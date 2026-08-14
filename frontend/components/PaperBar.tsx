"use client";

import type { ParseState, ResolveState } from "@/app/page";
import { UploadedPaper } from "@/lib/api";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function PaperBar({
  paper,
  parse,
  resolve,
  onRetry,
}: {
  paper: UploadedPaper;
  parse: ParseState;
  resolve: ResolveState;
  onRetry: () => void;
}) {
  return (
    <section className="stack">
      <div className="panel panel--control">
        <div className="control">
          <div className="control__file">
            <p className="panel__title">{paper.filename}</p>
            <p className="hint">
              <code>{paper.paper_id}</code> · {formatBytes(paper.size_bytes)}
            </p>
          </div>

          <div className="control__status">
            <Step
              label="Parsing the PDF"
              done={parse.phase === "ready"}
              busy={parse.phase === "extracting"}
              failed={parse.phase === "failed"}
            />
            <Step
              label="Checking references"
              done={resolve.phase === "done"}
              busy={resolve.phase === "checking"}
              failed={resolve.phase === "failed"}
            />
          </div>
        </div>

        {parse.phase === "extracting" && (
          <p className="hint">
            Reading the PDF and pulling out its structure and citations. A long
            paper can take 30–60 seconds.
          </p>
        )}

        {parse.phase === "ready" && resolve.phase === "checking" && (
          <p className="hint">
            Your paper is ready to read below. Each reference is now being looked
            up in OpenAlex and Semantic Scholar, which takes another 30–60
            seconds.
          </p>
        )}
      </div>

      {parse.phase === "failed" && (
        <div className="panel panel--error">
          <p className="panel__title">Could not parse this PDF</p>
          <p>{parse.message}</p>
          <button className="button" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </section>
  );
}

function Step({
  label,
  done,
  busy,
  failed,
}: {
  label: string;
  done: boolean;
  busy: boolean;
  failed: boolean;
}) {
  const state = failed ? "failed" : done ? "done" : busy ? "busy" : "waiting";

  return (
    <span className={`step step--${state}`}>
      <span className="step__dot" aria-hidden="true" />
      {label}
      {busy && "…"}
    </span>
  );
}
