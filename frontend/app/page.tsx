"use client";

import { useCallback, useEffect, useState } from "react";
import AgentPanel from "@/components/AgentPanel";
import DocumentPanel from "@/components/DocumentPanel";
import PaperBar from "@/components/PaperBar";
import PdfUploader from "@/components/PdfUploader";
import SplitPane from "@/components/SplitPane";
import {
  CurrentDocument,
  ExtractionResult,
  ResolutionResult,
  UploadedPaper,
  extractPaper,
  getDocument,
  resolvePaper,
} from "@/lib/api";

export type ParseState =
  | { phase: "extracting" }
  | { phase: "ready"; result: ExtractionResult }
  | { phase: "failed"; message: string };

export type ResolveState =
  | { phase: "idle" }
  | { phase: "checking" }
  | { phase: "done"; result: ResolutionResult }
  | { phase: "failed"; message: string };

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default function HomePage() {
  const [paper, setPaper] = useState<UploadedPaper | null>(null);
  const [parse, setParse] = useState<ParseState>({ phase: "extracting" });
  const [resolve, setResolve] = useState<ResolveState>({ phase: "idle" });
  const [current, setCurrent] = useState<CurrentDocument | null>(null);
  const [targeted, setTargeted] = useState<string[]>([]);

  const reset = useCallback(() => {
    setPaper(null);
    setParse({ phase: "extracting" });
    setResolve({ phase: "idle" });
    setCurrent(null);
    setTargeted([]);
  }, []);

  const runParse = useCallback(async (paperId: string) => {
    setParse({ phase: "extracting" });
    setResolve({ phase: "idle" });
    setTargeted([]);

    let extraction: ExtractionResult;
    try {
      extraction = await extractPaper(paperId);
    } catch (error) {
      setParse({ phase: "failed", message: messageOf(error) });
      return;
    }

    setParse({ phase: "ready", result: extraction });
    setCurrent({
      paper_id: extraction.paper_id,
      revision: extraction.document.revision,
      available_revisions: [extraction.document.revision],
      document: extraction.document,
    });

    if (extraction.references.length === 0) {
      setResolve({
        phase: "failed",
        message: "This paper has no references to check.",
      });
      return;
    }

    setResolve({ phase: "checking" });
    try {
      setResolve({ phase: "done", result: await resolvePaper(paperId) });
    } catch (error) {
      setResolve({ phase: "failed", message: messageOf(error) });
    }
  }, []);

  useEffect(() => {
    if (paper) void runParse(paper.paper_id);
  }, [paper, runParse]);

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
        <PdfUploader onUploaded={setPaper} />
      </main>
    );
  }

  const ready = parse.phase === "ready" && current !== null;
  const verified = resolve.phase === "done";

  return (
    <main className={`page${ready ? " page--split" : ""}`}>
      <div className="page__top">
        <div className="page__bar">
          <Header />
          <button className="button button--quiet" onClick={reset}>
            Upload a different paper
          </button>
        </div>
        <PaperBar
          paper={paper}
          parse={parse}
          resolve={resolve}
          onRetry={() => void runParse(paper.paper_id)}
        />
      </div>

      {ready && (
        <SplitPane
          leftLabel="The manuscript"
          rightLabel="Review and edit"
          left={
            <DocumentPanel
              extraction={parse.result}
              resolve={resolve}
              current={current}
              targetedBlocks={targeted}
            />
          }
          right={
            <AgentPanel
              paperId={paper.paper_id}
              revision={current.revision}
              verified={verified}
              checking={resolve.phase === "checking"}
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
