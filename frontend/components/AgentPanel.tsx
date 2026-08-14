"use client";

import { useState } from "react";
import EditPanel from "@/components/EditPanel";
import ReviewPanel from "@/components/ReviewPanel";

type Tab = "review" | "edit";

export default function AgentPanel({
  paperId,
  revision,
  verified,
  checking,
  onProposal,
  onApplied,
}: {
  paperId: string;
  revision: number;
  verified: boolean;
  checking: boolean;
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
        {checking && (
          <div className="panel panel--pending">
            <p className="panel__title">Still checking references…</p>
            <p className="hint">
              You can start now, but claims cannot be checked against their
              sources and the agent cannot add citations until this finishes.
            </p>
          </div>
        )}

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
