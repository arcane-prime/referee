from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NSMAP = {"tei": TEI_NS}

XML_ID = f"{{{XML_NS}}}id"


def local_name(element: etree._Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def find(element: etree._Element, xpath: str) -> etree._Element | None:
    matches = element.xpath(xpath, namespaces=NSMAP)
    return matches[0] if matches else None


def find_all(element: etree._Element, xpath: str) -> list[etree._Element]:
    return list(element.xpath(xpath, namespaces=NSMAP))


def text_of(element: etree._Element | None) -> str:
    if element is None:
        return ""
    return normalise_space("".join(element.itertext()))


def attr(element: etree._Element | None, name: str) -> str | None:
    if element is None:
        return None
    value = element.get(name)
    return value.strip() if value else None


def normalise_space(value: str) -> str:
    return " ".join(value.split())


# Notes
#
# Every TEI element is really named "{http://www.tei-c.org/ns/1.0}p" rather
# than "p". A lookup that forgets the namespace does not error; it silently
# matches nothing, which is the single most common way a TEI parser appears to
# work while returning empty documents. Routing every query through these
# helpers keeps the prefix in one place.
#
# local_name strips the namespace for tag comparisons. It also guards against
# comments and processing instructions, whose .tag is a callable rather than a
# string and would otherwise raise on rsplit.
#
# text_of collapses whitespace because PDF-derived TEI is full of line breaks
# from the original page layout. Those are an artefact of where words happened
# to fall on the page, not content, and preserving them would put phantom
# newlines in the middle of sentences.
