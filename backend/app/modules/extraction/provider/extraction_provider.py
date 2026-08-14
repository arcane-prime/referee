from datetime import datetime, timezone

from app.core.exceptions import NotExtractedError
from app.core.storage_provider import StorageProvider
from app.domain.document import Document
from app.domain.library import RawReference, Reference
from app.modules.extraction.dto.extraction_dto import (
    ExtractionResultDto,
    ExtractionSummaryDto,
    ReferenceSummaryDto,
)
from app.modules.extraction.provider.parser_backend import ParserBackend
from app.modules.extraction.provider.style_provider import StyleProvider
from app.modules.extraction.provider.tei_provider import TeiProvider


class ExtractionProvider:
    def __init__(
        self,
        storage: StorageProvider,
        parser: ParserBackend,
        tei_provider: TeiProvider,
        style_provider: StyleProvider,
    ) -> None:
        self._storage = storage
        self._parser = parser
        self._tei = tei_provider
        self._style = style_provider

    async def extract(self, paper_id: str, use_cached_tei: bool = False) -> ExtractionResultDto:
        tei_xml = self._storage.read_tei(paper_id) if use_cached_tei else None

        if tei_xml is None:
            pdf_bytes = self._storage.read_original(paper_id)
            tei_xml = await self._parser.parse(pdf_bytes, f"{paper_id}.pdf")
            self._storage.save_tei(paper_id, tei_xml)

        document, references = self._tei.parse(
            tei_xml=tei_xml,
            paper_id=paper_id,
            document_id=f"{paper_id}_rev0",
        )

        style, confidence = self._style.detect(document.cite_nodes())
        document = document.model_copy(
            update={"style": style, "style_confidence": confidence}
        )

        self._storage.save_revision(paper_id, 0, document.model_dump_json(indent=2))

        return ExtractionResultDto(
            paper_id=paper_id,
            extracted_at=datetime.now(timezone.utc),
            parser=self._parser.name,
            document=document,
            references=[Reference.from_raw(raw) for raw in references],
            summary=self._summarise(document, references),
        )

    def load_document(
        self, paper_id: str, revision: int | None = None
    ) -> tuple[Document, int]:
        number = (
            self._storage.latest_revision(paper_id) if revision is None else revision
        )
        payload = (
            None if number is None else self._storage.read_revision(paper_id, number)
        )

        if payload is None:
            raise NotExtractedError(
                f"Paper '{paper_id}' has not been extracted yet. Run extract first."
            )
        return Document.model_validate_json(payload), number

    def load_references(self, paper_id: str) -> list[RawReference]:
        tei_xml = self._storage.read_tei(paper_id)
        if tei_xml is None:
            raise NotExtractedError(
                f"Paper '{paper_id}' has not been extracted yet. Run extract first."
            )

        _, references = self._tei.parse(
            tei_xml=tei_xml,
            paper_id=paper_id,
            document_id=f"{paper_id}_rev0",
        )
        return references

    def _summarise(
        self,
        document: Document,
        references: list[RawReference],
    ) -> ExtractionSummaryDto:
        cite_nodes = document.cite_nodes()

        return ExtractionSummaryDto(
            section_count=len(document.sections),
            block_count=sum(1 for _ in document.blocks()),
            citation_count=len(cite_nodes),
            unlinked_citation_count=sum(1 for node in cite_nodes if not node.is_linked),
            references=ReferenceSummaryDto(
                total=len(references),
                good=sum(1 for ref in references if ref.parse_quality == "good"),
                degraded=sum(1 for ref in references if ref.parse_quality == "degraded"),
                failed=sum(1 for ref in references if ref.parse_quality == "failed"),
            ),
            detected_style=document.style,
            style_confidence=document.style_confidence,
        )
