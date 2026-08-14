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

/*
 Notes

 One renderer, used by both the manuscript and the edit diff. That is what
 makes a proposed change comparable to the text it replaces: a citation drawn
 in the diff is drawn by the same code that drew it in the paper, so a chip
 that looks identical is identical.

 Duplicating this per panel is how the two drift, and the drift would land
 exactly on the thing the user is trying to check.

 The switch is on the same `kind` discriminator the backend wrote. A citation
 is a chip carrying reference ids and the marker text never appears in the
 surrounding prose, because in the stored data it does not exist: "[12]" is
 produced at render time, here and by citeproc on export.

 Keys are array indices, which is safe here and nowhere else: these lists are
 rebuilt whole from the server on every change and never reordered in place, so
 an index is stable for as long as the list is.
*/
