"use client";

import { Block, Inline } from "@/lib/api";

export function InlineNode({ node }: { node: Inline }) {
  switch (node.kind) {
    case "text":
      return <>{node.text}</>;
    case "cite":
      return (
        <span
          className={`chip chip--cite${node.ref_ids.length === 0 ? " chip--unlinked" : ""}`}
          title={
            node.ref_ids.length
              ? `${node.raw_marker ?? ""} → ${node.ref_ids.join(", ")}`
              : `${node.raw_marker ?? ""} → not linked to any reference`
          }
        >
          {node.ref_ids.length ? node.ref_ids.join(", ") : "unlinked"}
        </span>
      );
    case "xref":
      return <span className="chip chip--xref">{node.label}</span>;
    case "math":
      return <span className="chip chip--math">{node.source}</span>;
  }
}

export function Inlines({ nodes }: { nodes: Inline[] }) {
  return (
    <>
      {nodes.map((node, index) => (
        <InlineNode key={index} node={node} />
      ))}
    </>
  );
}

export function BlockView({
  block,
  targeted,
}: {
  block: Block;
  targeted?: boolean;
}) {
  return (
    <p
      className={`block block--${block.kind}${targeted ? " block--targeted" : ""}`}
      id={`block-${block.id}`}
    >
      <span className="block__id">{block.id}</span>
      {block.label && <span className="block__label">{block.label}</span>}
      <Inlines nodes={block.inlines} />
    </p>
  );
}
