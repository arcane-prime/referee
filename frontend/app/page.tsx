"use client";

import { useState } from "react";
import ExtractionPanel from "@/components/ExtractionPanel";
import PdfUploader from "@/components/PdfUploader";
import { UploadedPaper } from "@/lib/api";

export default function HomePage() {
  const [paper, setPaper] = useState<UploadedPaper | null>(null);

  return (
    <main className="page">
      <header className="page__header">
        <h1>Referee</h1>
        <p>Upload a paper to check its citations against real databases.</p>
      </header>

      {paper ? (
        <>
          <ExtractionPanel paper={paper} />
          <button className="button button--quiet" onClick={() => setPaper(null)}>
            Upload a different paper
          </button>
        </>
      ) : (
        <PdfUploader onUploaded={setPaper} />
      )}
    </main>
  );
}

/*
 Notes

 The upload control is the homepage, not a landing page behind a call to
 action. A researcher arriving here should be one drop away from working.

 The page owns which paper is selected and nothing else. Upload and extraction
 are separate components because they are separate operations against separate
 endpoints, and collapsing them would make it easy to accidentally couple
 uploading to parsing.
*/
