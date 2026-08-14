"use client";

import { useCallback, useState } from "react";
import { ExtractionResult, UploadedPaper, extractPaper } from "@/lib/api";

type Status =
  | { phase: "idle" }
  | { phase: "extracting" }
  | { phase: "done" }
  | { phase: "error"; message: string };

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExtractionPanel({
  paper,
  extracted,
  onExtracted,
}: {
  paper: UploadedPaper;
  extracted: boolean;
  onExtracted: (result: ExtractionResult | null) => void;
}) {
  const [status, setStatus] = useState<Status>({ phase: "idle" });

  const runExtract = useCallback(async () => {
    setStatus({ phase: "extracting" });
    onExtracted(null);
    try {
      const result = await extractPaper(paper.paper_id);
      setStatus({ phase: "done" });
      onExtracted(result);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Something went wrong.";
      setStatus({ phase: "error", message });
    }
  }, [paper.paper_id, onExtracted]);

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

          <button
            className="button"
            onClick={() => void runExtract()}
            disabled={status.phase === "extracting"}
          >
            {status.phase === "extracting"
              ? "Extracting…"
              : extracted
                ? "Re-extract"
                : "Extract"}
          </button>
        </div>

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
    </section>
  );
}

/*
 Notes

 This is the control only. The parse it produces is rendered by DocumentPanel
 in the left pane, and this bar spans both panes above them, because the button
 acts on the whole workspace rather than on either side of it.

 Extraction fires only from this button. Uploading a file does not trigger it,
 so re-parsing after a parser change costs one click rather than a re-upload.

 The result is not held in this component's state. The page owns it, because
 both panes read it: the left renders it and the right derives from its
 verification status what the review and the agent are allowed to do. Storing
 it here as well would leave two copies to keep in step.

 The button says "Re-extract" once a parse exists, since at that point pressing
 it discards a document the user may have edited. Naming the destructive case
 differently is the cheapest warning available.
*/
