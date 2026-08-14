"use client";

import { useCallback, useEffect, useState } from "react";
import ExportPanel from "@/components/ExportPanel";
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

const MAX_CHANGES_PER_COMMAND = 8;

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
      onProposal(
        status.result.proposal.patches
          .map((patch) => patch.block_id)
          .filter((blockId) => approved.has(blockId)),
      );
    } else {
      onProposal([]);
    }
  }, [status, approved, onProposal]);

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
          than applied. One command changes at most{" "}
          {MAX_CHANGES_PER_COMMAND} paragraphs, so a whole-paper instruction
          will only reach the first few - run it again to continue.
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

      <ExportPanel paperId={paperId} revision={revision} />
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
        {proposal.patches.length + proposal.rejected.length >=
          MAX_CHANGES_PER_COMMAND && (
          <p className="hint hint--warn">
            This command reached the {MAX_CHANGES_PER_COMMAND}-paragraph limit,
            so later parts of the paper were not looked at. Run it again to
            continue.
          </p>
        )}
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
