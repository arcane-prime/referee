from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CSLType = Literal[
    "article-journal",
    "paper-conference",
    "book",
    "chapter",
    "thesis",
    "report",
    "webpage",
    "dataset",
    "manuscript",
    "document",
]


class CSLName(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    family: str | None = None
    given: str | None = None
    literal: str | None = None

    @property
    def surname(self) -> str | None:
        return self.family or self.literal


class CSLDate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_parts: list[list[int]] = Field(default_factory=list, alias="date-parts")
    raw: str | None = None

    @property
    def year(self) -> int | None:
        if self.date_parts and self.date_parts[0]:
            return self.date_parts[0][0]
        return None

    @classmethod
    def from_year(cls, year: int | None) -> "CSLDate | None":
        return cls(date_parts=[[year]]) if year is not None else None


class CSLItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: CSLType = "article-journal"

    title: str | None = None
    author: list[CSLName] = Field(default_factory=list)
    editor: list[CSLName] = Field(default_factory=list)

    container_title: str | None = Field(default=None, alias="container-title")
    collection_title: str | None = Field(default=None, alias="collection-title")
    publisher: str | None = None
    publisher_place: str | None = Field(default=None, alias="publisher-place")

    issued: CSLDate | None = None

    volume: str | None = None
    issue: str | None = None
    page: str | None = None

    DOI: str | None = None
    URL: str | None = None
    abstract: str | None = None
    note: str | None = None

    @property
    def year(self) -> int | None:
        return self.issued.year if self.issued else None

    @property
    def first_author_surname(self) -> str | None:
        return self.author[0].surname if self.author else None

    def to_csl_json(self) -> dict:
        payload = self.model_dump(by_alias=True, exclude_none=True)
        return {key: value for key, value in payload.items() if value != []}
