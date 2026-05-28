"""epub_lib.mathfix -- rewrite math constructs pandoc's MathML reader rejects.

Pandoc's TeX->MathML converter is stricter than LaTeX itself. When it fails
on a chunk it emits "Could not convert TeX math ..." and falls back to raw
TeX in the output -- ugly in an e-reader.

Every rule below was added in response to a real failure on a large book.
If you hit a new "Could not convert" warning, isolate the construct and add
a rule here.
"""
from __future__ import annotations

import re

from .common import DISPLAY_MATH_ENVS

# Custom bold macros that take no argument (\bmu == \bm{\mu}, etc.). Accents
# applied to these need explicit braces for pandoc: \hat\bmu -> \hat{\bmu}.
_BOLD_MACROS = ["bmu", "bSigma", "bx", "bX", "by", "bw", "bSigma", "btheta"]
_ACCENTS = ["hat", "tilde", "bar", "dot", "vec", "check"]

_MATH_ENV_RE = "|".join(e + r"\*?" for e in (
    DISPLAY_MATH_ENVS + ["aligned", "array", "cases", "split"]))


def _collapse_in_math_envs(s: str) -> str:
    """Inside math environments: \\emph->\\textit, '&&'->'&', booktabs
    rules -> \\hline. These are all things pandoc dislikes."""
    def clean(m: re.Match) -> str:
        b = m.group(0)
        b = re.sub(r"\\emph\{", r"\\textit{", b)
        b = b.replace("&&", "&")
        b = (b.replace("\\toprule", "\\hline")
              .replace("\\midrule", "\\hline")
              .replace("\\bottomrule", "\\hline"))
        return b
    for env in DISPLAY_MATH_ENVS + ["aligned", "array", "cases", "split"]:
        base = env
        s = re.sub(r"\\begin\{" + env + r"\*?\}.*?\\end\{" + base + r"\*?\}",
                   clean, s, flags=re.DOTALL)
    return s


def _promote_math_tables(s: str) -> str:
    r"""Convert  \[ \begin{array}{..} ... \end{array} \]  into a real
    `tabular` inside a `center` block.

    A small data table is sometimes typeset as a math `array`. Pandoc's
    MathML reader rejects the row/rule structure, so we promote it to an
    actual table, which pandoc renders as an HTML <table>.
    """
    def conv(m: re.Match) -> str:
        colspec = m.group(1)
        body = m.group(2)
        body = re.sub(r"\\(?:toprule|midrule|bottomrule)", r"\\hline", body)
        return ("\\begin{center}\n\\begin{tabular}{" + colspec + "}\n"
                + body.strip() + "\n\\end{tabular}\n\\end{center}")

    return re.sub(
        r"\\\[\s*\\begin\{array\}\{([^}]*)\}(.*?)\\end\{array\}\s*\\\]",
        conv, s, flags=re.DOTALL)


def fix(s: str) -> str:
    """Apply all math fixes to one chapter's LaTeX source."""
    # 1. \Bigl( \Bigr] etc. -> \left \right  (pandoc understands those)
    for big in ("Bigg", "Big", "bigg", "big"):
        s = s.replace(f"\\{big}l", "\\left").replace(f"\\{big}r", "\\right")

    # 2. \qed / \qedhere -- proof markers, meaningless in MathML
    s = s.replace("\\qedhere", "").replace("\\qed", "")

    # 3. accent over a no-arg bold macro needs braces
    for acc in _ACCENTS:
        for bm in _BOLD_MACROS:
            s = s.replace(f"\\{acc}\\{bm}", f"\\{acc}{{\\{bm}}}")
    # accent over \bm{...}: \hat\bm{x} -> \hat{\bm{x}}
    for acc in _ACCENTS:
        s = re.sub(rf"\\{acc}\\bm\{{([^}}]*)\}}",
                   rf"\\{acc}{{\\bm{{\1}}}}", s)

    # 4. old two-letter font switches inside braces -> \mathXX
    s = re.sub(r"\{\\rm\s+([^}]*)\}", r"\\mathrm{\1}", s)
    s = re.sub(r"\{\\bf\s+([^}]*)\}", r"\\mathbf{\1}", s)
    s = re.sub(r"\{\\it\s+([^}]*)\}", r"\\mathit{\1}", s)
    s = re.sub(r"\{\\sf\s+([^}]*)\}", r"\\mathsf{\1}", s)

    # 5. inside math envs: collapse && , \emph , booktabs rules
    s = _collapse_in_math_envs(s)

    # 5b. a display-math \[ \begin{array}...\end{array} \] that is really a
    #     data table (uses \toprule/\hline + \\ rows) -- pandoc's MathML
    #     reader chokes on it. Promote it to a real tabular.
    s = _promote_math_tables(s)

    # 6. flatten \textit/\emph/\textbf nested inside a math \text{...}
    def flatten(m: re.Match) -> str:
        inner = m.group(0)
        for cmd in ("textit", "emph", "textbf"):
            inner = re.sub(r"\\" + cmd + r"\{([^{}]*)\}", r"\1", inner)
        return inner
    s = re.sub(r"\\text\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", flatten, s)

    return s


def lift_math_labels(s: str) -> str:
    r"""Move \label{} out of display math.

    Pandoc keeps a \label that sits inside an equation environment as part
    of the math, so it surfaces in the MathML <annotation>. We pull each
    label out and emit a \hypertarget{...}{} immediately *before* the
    equation, which pandoc turns into a proper anchor element.
    """
    def handle(m: re.Match) -> str:
        block = m.group(0)
        labels = re.findall(r"\\label\{([^}]+)\}", block)
        if not labels:
            return block
        clean = re.sub(r"\\label\{[^}]+\}", "", block)
        anchors = "".join(f"\\hypertarget{{{l}}}{{}}" for l in labels)
        return anchors + clean

    for env in DISPLAY_MATH_ENVS:
        s = re.sub(r"\\begin\{" + env + r"\*?\}.*?\\end\{" + env + r"\*?\}",
                   handle, s, flags=re.DOTALL)
    # \[ ... \] display math
    s = re.sub(r"\\\[.*?\\\]", handle, s, flags=re.DOTALL)
    return s
