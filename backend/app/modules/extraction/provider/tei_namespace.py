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
