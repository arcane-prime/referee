"use client";

import { useState } from "react";
import EditPanel from "@/components/EditPanel";
import ReviewPanel from "@/components/ReviewPanel";

type Tab = "review" | "edit";

export default function AgentPanel({
  paperId,
  revision,
  verified,
  onProposal,
  onApplied,
}: {
  paperId: string;
  revision: number;
  verified: boolean;
  onProposal: (blockIds: string[]) => void;
  onApplied: () => void;
}) {
  const [tab, setTab] = useState<Tab>("review");

  return (
    <section className="agent">
      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "review"}
          className={`tabs__tab${tab === "review" ? " tabs__tab--active" : ""}`}
          onClick={() => setTab("review")}
        >
          Peer review
        </button>
        <button
          role="tab"
          aria-selected={tab === "edit"}
          className={`tabs__tab${tab === "edit" ? " tabs__tab--active" : ""}`}
          onClick={() => setTab("edit")}
        >
          Edit
        </button>
      </div>

      <div className="agent__body">
        {tab === "review" ? (
          <ReviewPanel paperId={paperId} verified={verified} />
        ) : (
          <EditPanel
            paperId={paperId}
            revision={revision}
            canCite={verified}
            onProposal={onProposal}
            onApplied={onApplied}
          />
        )}
      </div>
    </section>
  );
}

/*
 Notes

 Review and editing are two things a researcher does to the same manuscript, so
 they share one pane rather than competing for vertical space. The paper stays
 put on the left and the tool changes on the right, which matches how the work
 actually goes: read a finding, act on it, look at the paragraph again.

 Review is the default tab because it is the step that tells you what to edit.
 Opening on an empty command box would ask the user what they want before
 anything has told them.

 Both tabs are mounted lazily and unmount when switched away from, so a
 half-finished proposal does not sit in memory behind the review. That is a
 deliberate loss: switching tabs discards a prepared edit. Since nothing was
 written, re-running the command is cheap, and a stale proposal quietly
 surviving a tab switch would eventually be applied against a revision it was
 not computed from.
*/
