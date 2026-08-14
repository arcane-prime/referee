import re

from lxml import etree

from app.domain.document import CiteNode, Inline, MathNode, TextRun, XRefNode
from app.domain.geometry import BBox
from app.modules.extraction.provider.id_minter import IdMinter
from app.modules.extraction.provider.tei_namespace import local_name

DELIMITER_PAIRS = {"[": "]", "(": ")", "{": "}"}

GROUP_SEPARATORS = {"", ",", ";", "-", "–", "—", "‐", ",-", "·"}

DROPPED_REF_TYPES = {"foot"}

XREF_TYPES = {
    "figure": "figure",
    "table": "table",
    "formula": "equation",
    "section": "section",
}

BIBR_ID_PATTERN = re.compile(r"^b(\d+)$")
UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_]")

MAX_NORMALISE_PASSES = 4


def tei_target_to_ref_ids(target: str | None) -> list[str]:
    if not target:
        return []

    ref_ids: list[str] = []
    for token in target.split():
        raw = token.lstrip("#").strip()
        if not raw:
            continue
        match = BIBR_ID_PATTERN.match(raw)
        if match:
            ref_ids.append(f"ref_{match.group(1)}")
        else:
            ref_ids.append(f"ref_{UNSAFE_ID_CHARS.sub('_', raw)}")
    return ref_ids


def collapse_whitespace(text: str) -> str:
    if not text:
        return ""

    core = " ".join(text.split())
    if not core:
        return " " if text else ""

    leading = " " if text[0].isspace() else ""
    trailing = " " if text[-1].isspace() else ""
    return f"{leading}{core}{trailing}"


class InlineProvider:
    def __init__(self, minter: IdMinter) -> None:
        self._minter = minter

    def build_element(self, element: etree._Element) -> list[Inline]:
        return self._node_for(element)

    def build(self, element: etree._Element) -> list[Inline]:
        nodes = self._flatten(element)

        for _ in range(MAX_NORMALISE_PASSES):
            absorbed = self._absorb_delimiters(nodes)
            merged = self._merge_adjacent_citations(absorbed)
            if merged == nodes:
                break
            nodes = merged

        return self._coalesce(nodes)

    def _flatten(self, element: etree._Element) -> list[Inline]:
        nodes: list[Inline] = []

        if element.text:
            nodes.append(TextRun(text=collapse_whitespace(element.text)))

        for child in element:
            nodes.extend(self._node_for(child))
            if child.tail:
                nodes.append(TextRun(text=collapse_whitespace(child.tail)))

        return nodes

    def _node_for(self, element: etree._Element) -> list[Inline]:
        name = local_name(element)

        if name == "ref":
            return self._ref_node(element)

        if name == "formula":
            return [
                MathNode(
                    id=self._minter.mint("m"),
                    source=collapse_whitespace("".join(element.itertext())),
                    coords=BBox.parse_coords(element.get("coords")),
                )
            ]

        if name == "lb":
            return [TextRun(text=" ")]

        return self._flatten(element)

    def _ref_node(self, element: etree._Element) -> list[Inline]:
        ref_type = (element.get("type") or "").strip()
        label = collapse_whitespace("".join(element.itertext())).strip()
        coords = BBox.parse_coords(element.get("coords"))

        if ref_type in DROPPED_REF_TYPES:
            return []

        if ref_type == "bibr":
            return [
                CiteNode(
                    id=self._minter.mint("c"),
                    ref_ids=tei_target_to_ref_ids(element.get("target")),
                    raw_marker=label or None,
                    coords=coords,
                )
            ]

        if ref_type in XREF_TYPES:
            target = element.get("target")
            return [
                XRefNode(
                    id=self._minter.mint("x"),
                    target_kind=XREF_TYPES[ref_type],
                    target_id=target.lstrip("#") if target else None,
                    label=label,
                    coords=coords,
                )
            ]

        return [TextRun(text=label)] if label else []

    def _absorb_delimiters(self, nodes: list[Inline]) -> list[Inline]:
        result = list(nodes)

        for index, node in enumerate(result):
            if not isinstance(node, CiteNode):
                continue
            if index == 0 or index == len(result) - 1:
                continue

            before = result[index - 1]
            after = result[index + 1]
            if not isinstance(before, TextRun) or not isinstance(after, TextRun):
                continue

            for opener, closer in DELIMITER_PAIRS.items():
                trimmed_before = before.text.rstrip()
                trimmed_after = after.text.lstrip()

                if not trimmed_before.endswith(opener):
                    continue
                if not trimmed_after.startswith(closer):
                    continue

                result[index - 1] = TextRun(text=trimmed_before[:-1])
                result[index + 1] = TextRun(text=trimmed_after[1:])
                result[index] = node.model_copy(
                    update={"raw_marker": f"{opener}{node.raw_marker or ''}{closer}"}
                )
                break

        return result

    def _merge_adjacent_citations(self, nodes: list[Inline]) -> list[Inline]:
        result: list[Inline] = []
        index = 0

        while index < len(nodes):
            node = nodes[index]

            if not isinstance(node, CiteNode):
                result.append(node)
                index += 1
                continue

            group: list[CiteNode] = [node]
            markers: list[str] = [node.raw_marker or ""]
            cursor = index + 1

            while cursor < len(nodes):
                candidate = nodes[cursor]

                if isinstance(candidate, CiteNode):
                    group.append(candidate)
                    markers.append(candidate.raw_marker or "")
                    cursor += 1
                    continue

                is_separator = (
                    isinstance(candidate, TextRun)
                    and cursor + 1 < len(nodes)
                    and isinstance(nodes[cursor + 1], CiteNode)
                    and candidate.text.strip() in GROUP_SEPARATORS
                )
                if not is_separator:
                    break

                following = nodes[cursor + 1]
                assert isinstance(following, CiteNode)
                markers.append(candidate.text)
                markers.append(following.raw_marker or "")
                group.append(following)
                cursor += 2

            result.append(group[0] if len(group) == 1 else self._merge(group, markers))
            index = cursor

        return result

    def _merge(self, group: list[CiteNode], markers: list[str]) -> CiteNode:
        ref_ids: list[str] = []
        for node in group:
            for ref_id in node.ref_ids:
                if ref_id not in ref_ids:
                    ref_ids.append(ref_id)

        coords: list[BBox] = []
        for node in group:
            coords.extend(node.coords)

        marker = "".join(markers).strip()

        return CiteNode(
            id=group[0].id,
            ref_ids=ref_ids,
            raw_marker=marker or None,
            coords=coords,
        )

    def _coalesce(self, nodes: list[Inline]) -> list[Inline]:
        result: list[Inline] = []

        for node in nodes:
            if not isinstance(node, TextRun):
                result.append(node)
                continue

            if not node.text:
                continue

            if result and isinstance(result[-1], TextRun):
                merged_text = collapse_whitespace(result[-1].text + node.text)
                result[-1] = TextRun(text=merged_text)
                continue

            result.append(node)

        while result and isinstance(result[0], TextRun) and not result[0].text.strip():
            result.pop(0)
        while result and isinstance(result[-1], TextRun) and not result[-1].text.strip():
            result.pop()

        return result
