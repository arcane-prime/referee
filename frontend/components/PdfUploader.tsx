"use client";

import { useCallback, useRef, useState } from "react";
import { UploadedPaper, uploadPaper } from "@/lib/api";

type Status =
  | { phase: "idle" }
  | { phase: "uploading"; filename: string }
  | { phase: "error"; message: string };

export default function PdfUploader({
  onUploaded,
}: {
  onUploaded: (paper: UploadedPaper) => void;
}) {
  const [status, setStatus] = useState<Status>({ phase: "idle" });
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = useCallback(
    async (file: File) => {
      setStatus({ phase: "uploading", filename: file.name });
      try {
        const paper = await uploadPaper(file);
        setStatus({ phase: "idle" });
        onUploaded(paper);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Something went wrong.";
        setStatus({ phase: "error", message });
      }
    },
    [onUploaded],
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void submit(file);
    },
    [submit],
  );

  const isBusy = status.phase === "uploading";

  return (
    <section>
      <div
        className={`dropzone${isDragging ? " dropzone--active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-busy={isBusy}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void submit(file);
            event.target.value = "";
          }}
        />

        {isBusy ? (
          <p className="dropzone__label">Uploading {status.filename}…</p>
        ) : (
          <>
            <p className="dropzone__label">Drop a paper here</p>
            <p className="dropzone__hint">PDF, up to 50 MB</p>
          </>
        )}
      </div>

      {status.phase === "error" && (
        <div className="panel panel--error">
          <p className="panel__title">Upload failed</p>
          <p>{status.message}</p>
        </div>
      )}
    </section>
  );
}

/*
 Notes

 Uploading stores the file and nothing else. It does not trigger parsing, so
 this component never calls the extract endpoint and never knows it exists; it
 hands the caller a paper_id and stops.

 Status is one discriminated union rather than several booleans, so states such
 as "uploading and errored at the same time" cannot be represented.

 The file input is cleared after each selection. Without that, choosing the
 same file twice in a row fires no change event and the second attempt appears
 to do nothing.

 Client-side validation of the file type is intentionally absent. The server
 checks the PDF magic bytes, and duplicating a weaker version of that check
 here would only add a second place for the rule to drift.
*/
