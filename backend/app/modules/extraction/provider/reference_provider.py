import re

from lxml import etree

from app.domain.csl import CSLDate, CSLItem, CSLName, CSLType
from app.domain.geometry import BBox
from app.domain.library import RawReference
from app.modules.extraction.provider.inline_provider import tei_target_to_ref_ids
from app.modules.extraction.provider.tei_namespace import (
    XML_ID,
    attr,
    find,
    find_all,
    normalise_space,
    text_of,
)

YEAR_PATTERN = re.compile(r"(\d{4})")


class ReferenceProvider:
    def build_all(self, root: etree._Element) -> list[RawReference]:
        entries = find_all(root, ".//tei:text/tei:back//tei:listBibl/tei:biblStruct")
        return [self._build(entry, index) for index, entry in enumerate(entries)]

    def _build(self, entry: etree._Element, index: int) -> RawReference:
        ref_id = self._ref_id(entry, index)
        raw = self._raw_string(entry)

        return RawReference(
            id=ref_id,
            raw=raw,
            parsed=self._to_csl(entry, ref_id),
            coords=BBox.parse_coords(entry.get("coords")),
        )

    def _ref_id(self, entry: etree._Element, index: int) -> str:
        xml_id = entry.get(XML_ID)
        ref_ids = tei_target_to_ref_ids(xml_id)
        return ref_ids[0] if ref_ids else f"ref_{index}"

    def _raw_string(self, entry: etree._Element) -> str:
        note = find(entry, "./tei:note[@type='raw_reference']")
        raw = text_of(note)
        if raw:
            return raw
        return normalise_space("".join(entry.itertext()))

    def _to_csl(self, entry: etree._Element, ref_id: str) -> CSLItem | None:
        analytic_title = text_of(find(entry, "./tei:analytic/tei:title[@level='a']"))
        monograph_title = text_of(find(entry, "./tei:monogr/tei:title[@level='m']"))
        journal_title = text_of(find(entry, "./tei:monogr/tei:title[@level='j']"))

        title = analytic_title or monograph_title or journal_title
        authors = self._authors(entry)
        issued = self._issued(entry)

        if not title and not authors and not issued:
            return None

        container = ""
        if analytic_title:
            container = journal_title or monograph_title
        elif monograph_title and journal_title:
            container = journal_title

        return CSLItem(
            id=ref_id,
            type=self._csl_type(entry, analytic_title, journal_title),
            title=title or None,
            author=authors,
            container_title=container or None,
            publisher=text_of(find(entry, "./tei:monogr/tei:imprint/tei:publisher")) or None,
            issued=issued,
            volume=self._scope(entry, "volume"),
            issue=self._scope(entry, "issue"),
            page=self._pages(entry),
            DOI=self._idno(entry, "DOI"),
            URL=self._idno(entry, "URL") or self._target_url(entry),
        )

    def _csl_type(
        self,
        entry: etree._Element,
        analytic_title: str,
        journal_title: str,
    ) -> CSLType:
        if find(entry, "./tei:monogr/tei:meeting") is not None:
            return "paper-conference"
        if analytic_title and journal_title:
            return "article-journal"
        if not analytic_title:
            return "book"
        return "article-journal"

    def _authors(self, entry: etree._Element) -> list[CSLName]:
        persons = find_all(entry, "./tei:analytic/tei:author/tei:persName")
        if not persons:
            persons = find_all(entry, "./tei:monogr/tei:author/tei:persName")

        names: list[CSLName] = []
        for person in persons:
            surname = text_of(find(person, "./tei:surname"))
            forenames = [text_of(node) for node in find_all(person, "./tei:forename")]
            given = " ".join(part for part in forenames if part)

            if surname:
                names.append(CSLName(family=surname, given=given or None))
                continue

            literal = text_of(person)
            if literal:
                names.append(CSLName(literal=literal))

        if names:
            return names

        organisations = find_all(entry, ".//tei:author/tei:orgName")
        return [CSLName(literal=text_of(org)) for org in organisations if text_of(org)]

    def _issued(self, entry: etree._Element) -> CSLDate | None:
        date = find(entry, "./tei:monogr/tei:imprint/tei:date")
        if date is None:
            date = find(entry, ".//tei:date")
        if date is None:
            return None

        candidate = attr(date, "when") or text_of(date)
        if not candidate:
            return None

        match = YEAR_PATTERN.search(candidate)
        if not match:
            return CSLDate(raw=candidate)
        return CSLDate(date_parts=[[int(match.group(1))]], raw=candidate)

    def _scope(self, entry: etree._Element, unit: str) -> str | None:
        node = find(entry, f".//tei:biblScope[@unit='{unit}']")
        if node is None:
            return None
        return text_of(node) or attr(node, "from") or None

    def _pages(self, entry: etree._Element) -> str | None:
        node = find(entry, ".//tei:biblScope[@unit='page']")
        if node is None:
            return None

        text = text_of(node)
        if text:
            return text

        start = attr(node, "from")
        end = attr(node, "to")
        if start and end:
            return f"{start}-{end}"
        return start or end

    def _idno(self, entry: etree._Element, kind: str) -> str | None:
        node = find(entry, f".//tei:idno[@type='{kind}']")
        return text_of(node) or None

    def _target_url(self, entry: etree._Element) -> str | None:
        node = find(entry, ".//tei:ptr[@target]")
        return attr(node, "target")
