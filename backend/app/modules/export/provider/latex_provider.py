import unicodedata

from app.domain.document import (
    Block,
    CiteNode,
    Document,
    MathNode,
    Section,
    TextRun,
    XRefNode,
)

ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

SYMBOLS = {
    "•": r"\textbullet{}",
    "‐": "-",
    "‑": "-",
    "−": "-",
    "–": "--",
    "—": "---",
    "‘": "`",
    "’": "'",
    "“": "``",
    "”": "''",
    "…": r"\ldots{}",
    "†": r"\dag{}",
    "‡": r"\ddag{}",
    "→": r"\ensuremath{\rightarrow}",
    "←": r"\ensuremath{\leftarrow}",
    "↔": r"\ensuremath{\leftrightarrow}",
    "≤": r"\ensuremath{\leq}",
    "≥": r"\ensuremath{\geq}",
    "≈": r"\ensuremath{\approx}",
    "≠": r"\ensuremath{\neq}",
    "×": r"\ensuremath{\times}",
    "÷": r"\ensuremath{\div}",
    "±": r"\ensuremath{\pm}",
    "∞": r"\ensuremath{\infty}",
    "∈": r"\ensuremath{\in}",
    "∑": r"\ensuremath{\sum}",
    "∏": r"\ensuremath{\prod}",
    "√": r"\ensuremath{\sqrt{}}",
    "°": r"\ensuremath{^\circ}",
}

SECTION_COMMANDS = {1: "section", 2: "subsection", 3: "subsubsection"}


def fold(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text)
    return "".join(SYMBOLS.get(character, character) for character in folded)


def escape(text: str) -> str:
    escaped = "".join(ESCAPES.get(character, character) for character in text)
    return fold(escaped)


def render_inline(node) -> str:
    if isinstance(node, TextRun):
        return escape(node.text)

    if isinstance(node, CiteNode):
        if not node.ref_ids:
            return ""
        return "\\cite{" + ",".join(node.ref_ids) + "}"

    if isinstance(node, MathNode):
        return f"${fold(node.source)}$"

    if isinstance(node, XRefNode):
        return escape(node.label)

    return ""


def render_block(block: Block) -> str:
    body = "".join(render_inline(node) for node in block.inlines).strip()
    if not body:
        return ""

    if block.kind == "heading":
        return ""

    if block.kind == "abstract":
        return f"\\begin{{abstract}}\n{body}\n\\end{{abstract}}"

    if block.kind == "formula":
        inner = body.strip("$")
        return f"\\begin{{equation}}\n{inner}\n\\end{{equation}}"

    if block.kind == "caption":
        return f"\\begin{{quote}}\n\\small {body}\n\\end{{quote}}"

    return body


def render_section(section: Section) -> str:
    command = SECTION_COMMANDS.get(section.level, "paragraph")
    heading = section.title and not _is_self_titling(section)
    parts = [f"\\{command}{{{escape(section.title)}}}"] if heading else []

    for block in section.blocks:
        rendered = render_block(block)
        if rendered:
            parts.append(rendered)

    return "\n\n".join(parts)


def _is_self_titling(section: Section) -> bool:
    kinds = {block.kind for block in section.blocks if block.inlines}
    return kinds == {"abstract"}


def render_document(
    document: Document,
    bibliography: list[tuple[str, str]],
    style_name: str,
) -> str:
    body = "\n\n".join(
        rendered
        for rendered in (render_section(section) for section in document.sections)
        if rendered.strip()
    )

    authors = " \\and ".join(escape(author) for author in document.authors)

    return "\n".join(
        [
            "\\documentclass[11pt]{article}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage{amsmath,amssymb}",
            "\\usepackage{hyperref}",
            "",
            f"\\title{{{escape(document.title)}}}",
            f"\\author{{{authors}}}" if authors else "\\author{}",
            "",
            "\\begin{document}",
            "\\maketitle",
            "",
            body,
            "",
            render_bibliography(bibliography, style_name),
            "\\end{document}",
            "",
        ]
    )


def render_bibliography(entries: list[tuple[str, str]], style_name: str) -> str:
    if not entries:
        return ""

    widest = str(len(entries))
    lines = [
        f"% Bibliography rendered by citeproc from {style_name}.csl",
        f"\\begin{{thebibliography}}{{{widest}}}",
    ]

    for ref_id, rendered in entries:
        lines.append(f"\\bibitem{{{ref_id}}}")
        lines.append(escape(rendered))
        lines.append("")

    lines.append("\\end{thebibliography}")
    lines.append("")
    return "\n".join(lines)
