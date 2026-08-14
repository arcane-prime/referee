"use client";

import { useCallback, useState } from "react";
import AgentPanel from "@/components/AgentPanel";
import DocumentPanel from "@/components/DocumentPanel";
import ExtractionPanel from "@/components/ExtractionPanel";
import PdfUploader from "@/components/PdfUploader";
import SplitPane from "@/components/SplitPane";
import {
  CurrentDocument,
  ExtractionResult,
  UploadedPaper,
  getDocument,
} from "@/lib/api";

export default function HomePage() {
  const [paper, setPaper] = useState<UploadedPaper | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [current, setCurrent] = useState<CurrentDocument | null>(null);
  const [targeted, setTargeted] = useState<string[]>([]);

  const reset = useCallback(() => {
    setPaper(null);
    setExtraction(null);
    setCurrent(null);
    setTargeted([]);
  }, []);

  const onUploaded = useCallback((uploaded: UploadedPaper) => {
    setExtraction(null);
    setCurrent(null);
    setTargeted([]);
    setPaper(uploaded);
  }, []);

  const onExtracted = useCallback(
    (result: ExtractionResult | null) => {
      setExtraction(result);
      setTargeted([]);
      setCurrent(
        result === null
          ? null
          : {
              paper_id: result.paper_id,
              revision: result.document.revision,
              available_revisions: [result.document.revision],
              document: result.document,
            },
      );
    },
    [],
  );

  const refresh = useCallback(async () => {
    if (!paper) return;
    setTargeted([]);
    try {
      setCurrent(await getDocument(paper.paper_id));
    } catch {
      setCurrent(null);
    }
  }, [paper]);

  if (!paper) {
    return (
      <main className="page">
        <Header />
        <PdfUploader onUploaded={onUploaded} />
      </main>
    );
  }

  const ready = extraction !== null && current !== null;

  return (
    <main className={`page${ready ? " page--split" : ""}`}>
      <div className="page__top">
        <div className="page__bar">
          <Header />
          <button className="button button--quiet" onClick={reset}>
            Upload a different paper
          </button>
        </div>
        <ExtractionPanel
          paper={paper}
          extracted={ready}
          onExtracted={onExtracted}
        />
      </div>

      {ready && (
        <SplitPane
          leftLabel="The manuscript"
          rightLabel="Review and edit"
          left={
            <DocumentPanel
              extraction={extraction}
              current={current}
              targetedBlocks={targeted}
            />
          }
          right={
            <AgentPanel
              paperId={paper.paper_id}
              revision={current.revision}
              verified={extraction.verification.succeeded}
              onProposal={setTargeted}
              onApplied={() => void refresh()}
            />
          }
        />
      )}
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

 The journey the brief describes, in one screen: upload, see the parse, read
 the review, instruct an edit, approve it. Only the upload is a separate
 screen, because until a file exists there is nothing to show beside it.

 Two pieces of state that look similar are deliberately separate. `extraction`
 is a fact about the parse and never changes after it is produced; `current` is
 the manuscript, which every approved edit replaces. Merging them would mean
 re-running extraction to see the result of an edit, and that would call GROBID
 and the literature databases to rebuild a document already on disk.

 After an edit is applied the page re-reads the document rather than patching
 its own copy from the response. The server has just written a revision, and
 rebuilding the client's idea of the paper from anything other than that file
 is how the two come to disagree.

 `targeted` flows up from the edit panel and down into the manuscript, so the
 blocks a pending proposal would change are highlighted in the paper itself.
 The researcher sees which of their paragraphs an instruction selected before
 approving anything, which is the cheapest check on a planner that chose badly.

 The layout changes shape once a parse exists: a narrow reading column before,
 two independently scrolling panes after. Stacked, every comparison between a
 finding and the sentence it refers to costs a long scroll.

 Starting a new extraction clears the parse before the request goes out, so the
 agent pane cannot sit beside a manuscript that is being replaced. A request
 completing late would otherwise repopulate it with findings belonging to a
 different paper.
*/
