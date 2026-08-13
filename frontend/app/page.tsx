"use client";

import { useCallback, useState } from "react";
import ExtractionPanel from "@/components/ExtractionPanel";
import PdfUploader from "@/components/PdfUploader";
import ReviewPanel from "@/components/ReviewPanel";
import { ExtractionResult, UploadedPaper } from "@/lib/api";

export default function HomePage() {
  const [paper, setPaper] = useState<UploadedPaper | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);

  const reset = useCallback(() => {
    setPaper(null);
    setExtraction(null);
  }, []);

  const onUploaded = useCallback((uploaded: UploadedPaper) => {
    setExtraction(null);
    setPaper(uploaded);
  }, []);

  if (!paper) {
    return (
      <main className="page">
        <Header />
        <PdfUploader onUploaded={onUploaded} />
      </main>
    );
  }

  return (
    <main className="page">
      <Header />

      <ExtractionPanel paper={paper} onExtracted={setExtraction} />

      {extraction && (
        <ReviewPanel
          paperId={paper.paper_id}
          verified={extraction.verification.succeeded}
        />
      )}

      <button className="button button--quiet" onClick={reset}>
        Upload a different paper
      </button>
    </main>
  );
}

function Header() {
  return (
    <header className="page__header">
      <h1>Referee</h1>
      <p>Upload a paper to check its citations against real databases.</p>
    </header>
  );
}

/*
 Notes

 Two user actions, matching the brief's journey: see the parse, then request a
 review. Checking references against the literature databases happens as part
 of producing the parse rather than as a step the user triggers, because there
 is no decision being offered there. A researcher always wants their references
 checked, and a control with only one sensible answer should not exist.

 When the databases are unreachable the parse still succeeds and says so, and
 the review panel adjusts what it offers to match. What the review can do is
 derived from whether verification worked, rather than asked of a user who has
 no way to know the right answer.

 Starting a new extraction clears the previous result before the request goes
 out, so the review panel cannot sit under a parse that is being replaced. An
 earlier request completing late would otherwise repopulate it with findings
 belonging to a different paper.

 The review panel appears only once a parse exists, which is a real dependency
 rather than a cosmetic one: there is nothing to review until the document has
 been extracted.

 The upload control is the homepage rather than a landing page behind a call to
 action. A researcher arriving here should be one drop away from working.
*/
