"use client";

import { useCallback, useEffect, useState } from "react";
import { Inlines } from "@/components/InlineNodes";
import {
  BlockPatch,
  CitationDelta,
  OperationKind,
  ProposalResult,
  RejectedOperation,
  applyEdit,
  planEdit,
} from "@/lib/api";

const EXAMPLES = [
  "make the introduction shorter",
  "tighten the related work section",
  "make the conclusion more concise",
];

const OPERATION_LABEL: Record<OperationKind, string> = {
  shorten_block: "shortened",
  rewrite_block: "rewritten",
  add_citation: "citation added",
  delete_block: "deleted",
};

type Status =
  | { phase: "idle" }
  | { phase: "planning" }
  | { phase: "ready"; result: ProposalResult }
  | { phase: "applying"; result: ProposalResult }
  | { phase: "applied"; message: string }
  | { phase: "error"; message: string };

export default function EditPanel({
  paperId,
  revision,
  canCite,
  onProposal,
  onApplied,
}: {
  paperId: string;
  revision: number;
  canCite: boolean;
  onProposal: (blockIds: string[]) => void;
  onApplied: () => void;
}) {
  const [command, setCommand] = useState("");
  const [status, setStatus] = useState<Status>({ phase: "idle" });
  const [approved, setApproved] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (status.phase === "ready" || status.phase === "applying") {
      onProposal(status.result.proposal.patches.map((patch) => patch.block_id));
    } else {
      onProposal([]);
    }
  }, [status, onProposal]);

  const plan = useCallback(async () => {
    const instruction = command.trim();
    if (!instruction) return;

    setStatus({ phase: "planning" });
    try {
      const result = await planEdit(paperId, instruction);
      setApproved(new Set(result.proposal.patches.map((p) => p.block_id)));
      setStatus({ phase: "ready", result });
    } catch (error) {
      setStatus({
        phase: "error",
        message: error instanceof Error ? error.message : "Something went wrong.",
      });
    }
  }, [paperId, command]);

  const confirm = useCallback(
    async (result: ProposalResult) => {
      setStatus({ phase: "applying", result });
      try {
        const applied = await applyEdit(
          paperId,
          result.proposal,
          [...approved],
        );
        setStatus({ phase: "applied", message: applied.message });
        setCommand("");
        setApproved(new Set());
        onApplied();
      } catch (error) {
        setStatus({
          phase: "error",
          message:
            error instanceof Error ? error.message : "Something went wrong.",
        });
      }
    },
    [paperId, approved, onApplied],
  );

  const toggle = useCallback((blockId: string) => {
    setApproved((current) => {
      const next = new Set(current);
      if (next.has(blockId)) {
        next.delete(blockId);
      } else {
        next.add(blockId);
      }
      return next;
    });
  }, []);

  const busy = status.phase === "planning" || status.phase === "applying";

  return (
    <div className="stack">
      <div className="panel">
        <p className="panel__title">Edit by instruction</p>
        <p className="hint">
          Describe a change in plain English. Nothing is written until you
          approve it, and any edit that would drop a citation is refused rather
          than applied.
        </p>

        <textarea
          className="command"
          rows={2}
          value={command}
          placeholder="make the introduction shorter"
          disabled={busy}
          onChange={(event) => setCommand(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void plan();
            }
          }}
        />

        <div className="command__row">
          <button
            className="button"
            onClick={() => void plan()}
            disabled={busy || !command.trim()}
          >
            {status.phase === "planning" ? "Preparing…" : "Prepare changes"}
          </button>
          <span className="hint">Working from revision {revision}</span>
        </div>

        {!canCite && (
          <p className="hint hint--warn">
            References were not verified, so the agent cannot add citations. It
            can still shorten and rewrite.
          </p>
        )}

        <div className="examples">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              className="examples__item"
              disabled={busy}
              onClick={() => setCommand(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {status.phase === "error" && (
        <div className="panel panel--error">
          <p className="panel__title">That change was not applied</p>
          <p>{status.message}</p>
        </div>
      )}

      {status.phase === "applied" && (
        <div className="panel panel--ok">
          <p className="panel__title">Applied</p>
          <p className="hint">{status.message}</p>
        </div>
      )}

      {(status.phase === "ready" || status.phase === "applying") && (
        <Proposal
          result={status.result}
          approved={approved}
          busy={status.phase === "applying"}
          onToggle={toggle}
          onConfirm={() => void confirm(status.result)}
          onDiscard={() => setStatus({ phase: "idle" })}
        />
      )}
    </div>
  );
}

function Proposal({
  result,
  approved,
  busy,
  onToggle,
  onConfirm,
  onDiscard,
}: {
  result: ProposalResult;
  approved: Set<string>;
  busy: boolean;
  onToggle: (blockId: string) => void;
  onConfirm: () => void;
  onDiscard: () => void;
}) {
  const { proposal } = result;

  return (
    <>
      <div className="panel">
        <p className="panel__title">Proposed changes</p>
        <p className="hint">{result.message}</p>
        <CitationSummary delta={proposal.citations} />
      </div>

      {proposal.patches.map((patch) => (
        <PatchCard
          key={patch.block_id}
          patch={patch}
          approved={approved.has(patch.block_id)}
          disabled={busy}
          onToggle={() => onToggle(patch.block_id)}
        />
      ))}

      {proposal.rejected.map((rejection) => (
        <RefusedCard key={rejection.block_id} rejection={rejection} />
      ))}

      {proposal.patches.length > 0 && (
        <div className="panel approve">
          <button
            className="button"
            onClick={onConfirm}
            disabled={busy || approved.size === 0}
          >
            {busy
              ? "Applying…"
              : `Apply ${approved.size} change${approved.size === 1 ? "" : "s"}`}
          </button>
          <button className="button button--quiet" onClick={onDiscard} disabled={busy}>
            Discard
          </button>
        </div>
      )}
    </>
  );
}

function PatchCard({
  patch,
  approved,
  disabled,
  onToggle,
}: {
  patch: BlockPatch;
  approved: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={`panel patch${approved ? " patch--approved" : ""}`}>
      <div className="patch__head">
        <label className="patch__approve">
          <input
            type="checkbox"
            checked={approved}
            disabled={disabled}
            onChange={onToggle}
          />
          <span>{approved ? "Will apply" : "Skipped"}</span>
        </label>
        <span className="tag">{OPERATION_LABEL[patch.operation]}</span>
        <code className="patch__anchor">{patch.block_id}</code>
      </div>

      <div className="patch__side patch__side--before">
        <span className="patch__label">Before</span>
        <p className="patch__text">
          <Inlines nodes={patch.before} />
        </p>
      </div>

      <div className="patch__side patch__side--after">
        <span className="patch__label">After</span>
        {patch.deleted ? (
          <p className="patch__text patch__text--deleted">
            This paragraph would be removed.
          </p>
        ) : (
          <p className="patch__text">
            <Inlines nodes={patch.after} />
          </p>
        )}
      </div>

      <CitationSummary delta={patch.citations} />
    </div>
  );
}

function RefusedCard({ rejection }: { rejection: RejectedOperation }) {
  return (
    <div className="panel panel--warn">
      <div className="patch__head">
        <span className="tag tag--refused">refused</span>
        <code className="patch__anchor">{rejection.block_id}</code>
      </div>
      <p className="hint">{rejection.reason}</p>
    </div>
  );
}

function CitationSummary({ delta }: { delta: CitationDelta }) {
  if (delta.added.length === 0 && delta.removed.length === 0 && delta.moved.length === 0) {
    return <p className="citations citations--intact">Citations unchanged</p>;
  }

  return (
    <p className="citations">
      {delta.added.length > 0 && (
        <span className="citations__added">+{delta.added.length} added</span>
      )}
      {delta.removed.length > 0 && (
        <span className="citations__removed">−{delta.removed.length} removed</span>
      )}
      {delta.moved.length > 0 && (
        <span className="citations__moved">{delta.moved.length} moved</span>
      )}
    </p>
  );
}

/*
 Notes

 The command box is the whole of stage 4's input. Everything else on this panel
 exists to let a researcher decide whether to accept what came back, which is
 the point the brief is most insistent about: the human stays in the loop.

 Every patch is shown as before and after rendered with the same component the
 manuscript uses, so citation chips in the diff are drawn by the same code that
 drew them in the paper. A citation that moved is visible as a chip in a
 different place rather than as a claim in a summary line.

 Patches start ticked and can be unticked. The alternative, starting unticked,
 reads as though the tool is unsure about its own output; the useful default is
 "apply what I asked for, minus anything I object to". The approved set is sent
 explicitly rather than relying on the server's "absent means all", because in
 a UI with checkboxes those two are only the same until someone unticks one.

 Refused operations get a card of their own rather than being hidden. If the
 model returned a rewrite that would have dropped [[c_4]], the researcher is
 told which block and why. An edit that quietly did less than it claimed is the
 exact failure this stage was built to prevent, so it would be perverse to hide
 the evidence that the guard worked.

 The panel reports when the agent cannot add citations at all, which happens
 when verification failed and the library holds nothing with an external id.
 Saying so before a command is issued is better than a refusal that looks like
 a bug.

 onProposal lifts the targeted block ids to the page so the manuscript pane can
 highlight them. The diff says what would change; the highlight says where in
 their paper it is.
*/
