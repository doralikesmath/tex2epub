"""epub_lib.common -- small shared helpers."""
from __future__ import annotations

import re
from pathlib import Path

# Custom theorem-like environments commonly defined with \newtcbtheorem or
# \newtheorem. Map: environment name -> (display label, \ref prefix).
# Extend this if your book defines others.
THEOREM_ENVS = {
    "definition":  ("Definition",          "def"),
    "theorem":     ("Theorem",             "thm"),
    "proposition": ("Proposition",         "prop"),
    "lemma":       ("Lemma",               "lem"),
    "corollary":   ("Corollary",           "cor"),
    "example":     ("Example",             "ex"),
    "remark":      ("Remark",              "rem"),
    "warning":     ("Practitioner Warning", "warn"),
    # book-specific boxes -- harmless if unused:
    "shapbox":     ("SHAP Insight",        "shap"),
    "nlpbox":      ("NLP Insight",         "nlp"),
    "llmbox":      ("LLM Application",     "llm"),
}

# Display-math environments whose \label{} must be lifted out so pandoc
# does not bury it inside the MathML <annotation>.
DISPLAY_MATH_ENVS = ["equation", "align", "gather", "multline", "eqnarray"]


def split_preamble(main_tex: Path) -> tuple[str, str]:
    """Return (preamble, body) of the LaTeX root file.

    preamble = everything up to (not incl.) \\begin{document}
    body     = \\begin{document} ... end of file
    """
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    marker = "\\begin{document}"
    i = text.index(marker)
    return text[:i], text[i:]


def chapter_input_order(body: str) -> list[str]:
    r"""Filenames pulled in by \input{...} / \include{...}, in order.

    Returns paths *as written* (without forcing a .tex extension).
    """
    return re.findall(r"\\(?:input|include)\{([^}]+)\}", body)


def iter_tex_files(chapters_dir: Path):
    """Yield .tex files in a directory, sorted by filename."""
    for p in sorted(chapters_dir.glob("*.tex")):
        yield p


def balanced_group(text: str, open_idx: int) -> tuple[str, int]:
    """Given text and the index of an opening '{', return (group, end_idx)
    where group includes both braces and end_idx is just past the close."""
    assert text[open_idx] == "{"
    depth = 0
    j = open_idx
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx:j + 1], j + 1
        j += 1
    raise ValueError("unbalanced braces")


def sanitize_id(value: str) -> str:
    """EPUB id/fragment values may not contain whitespace."""
    return re.sub(r"\s+", "-", value.strip())
