"""epub_lib.preprocess -- prepare LaTeX sources for pandoc.

For every chapter file it:
  * replaces each tikzpicture with \\includegraphics of the rendered PNG
  * converts theorem-like environments to a bold lead-in + blockquote
  * lifts \\label out of display math, applies math fixes (see mathfix.py)

It also writes `epub_master.tex` -- a thin root file that \\input's the
preprocessed chapters and carries only the math macros pandoc needs.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import (THEOREM_ENVS, split_preamble, chapter_input_order,
                     balanced_group)
from . import mathfix


def _anchor_float_labels(txt: str) -> str:
    r"""Add a \hypertarget anchor for \label{} that lives inside a figure
    or lstlisting float.

    Pandoc does not carry figure/listing labels as anchors, so a
    \ref{fig:..} / \ref{lst:..} would point at nothing. We prepend an
    explicit \hypertarget right before the float.
    """
    # figures: \label anywhere inside \begin{figure}...\end{figure}
    def fig(m: re.Match) -> str:
        block = m.group(0)
        labels = re.findall(r"\\label\{([^}]+)\}", block)
        anchors = "".join(f"\\hypertarget{{{l}}}{{}}\n" for l in labels)
        return anchors + block
    txt = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", fig, txt,
                 flags=re.DOTALL)

    # listings: label is given in the option list, label={lst:..}
    def lst(m: re.Match) -> str:
        opts = m.group(0)
        labels = re.findall(r"label=\{([^}]+)\}", opts)
        anchors = "".join(f"\\hypertarget{{{l}}}{{}}\n\n" for l in labels)
        return anchors + opts
    txt = re.sub(r"\\begin\{lstlisting\}\[[^\]]*\]", lst, txt)
    return txt


def _chapter_dir(book_root: Path) -> Path:
    """Prefer a `chapters/` subdir; else the candidate with most .tex
    files (avoids picking a root that holds only main.tex)."""
    best, best_n = book_root, -1
    for d in (book_root / "chapters", book_root):
        if d.is_dir():
            n = len(list(d.glob("*.tex")))
            if n > best_n:
                best, best_n = d, n
    return best


def _global_figure_index(book_root: Path) -> dict[str, int]:
    """Map chapter filename -> index of its first figure in the global,
    sorted-filename ordering used by figures.render_all()."""
    chap_dir = _chapter_dir(book_root)
    idx: dict[str, int] = {}
    running = 0
    for f in sorted(chap_dir.glob("*.tex")):
        idx[f.name] = running
        txt = f.read_text(encoding="utf-8", errors="replace")
        running += len(re.findall(r"\\begin\{tikzpicture\}", txt))
    return idx


def _replace_tikz(txt: str, base: int) -> str:
    """Swap each tikzpicture for an \\includegraphics, numbered from `base`."""
    counter = [0]

    def repl(_m: re.Match) -> str:
        i = base + counter[0]
        counter[0] += 1
        return (f"\\includegraphics[width=0.85\\linewidth]"
                f"{{img/fig{i:02d}.png}}")

    return re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}",
                  repl, txt, flags=re.DOTALL)


def _convert_theorem_boxes(txt: str) -> str:
    r"""Turn  \begin{definition}{Title}{key} ... \end{definition}
    into a bold lead-in plus a quote block, with a \hypertarget anchor:

        \textbf{Definition (Title).}\quad \hypertarget{def:key}{}
        \begin{quote} ... \end{quote}

    Works for any environment in THEOREM_ENVS. The 3-argument form
    {Title}{key} matches the `\newtcbtheorem` convention; if your book
    uses `\newtheorem` the key comes from a following \label instead --
    extend this function for that case.
    """
    for env, (label, prefix) in THEOREM_ENVS.items():
        pat = re.compile(
            r"\\begin\{" + env + r"\}\s*"
            r"\{((?:[^{}]|\{[^{}]*\})*)\}\s*"   # {Title} (one nesting level)
            r"\{([^}]*)\}")                      # {key}

        def opener(m: re.Match, label=label, prefix=prefix) -> str:
            title = m.group(1).strip()
            key = m.group(2).strip()
            head = label + (f" ({title})" if title else "")
            anchor = f"\\hypertarget{{{prefix}:{key}}}{{}}"
            return (f"\n\n\\textbf{{{head}.}}\\quad {anchor}\n"
                    f"\\begin{{quote}}\n")

        txt = pat.sub(opener, txt)
        txt = txt.replace(f"\\end{{{env}}}", "\n\\end{quote}\n")
    return txt


def _detect_title(main_tex: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    for pat in (r"\\title\{([^}]+)\}", r"pdftitle=\{([^}]+)\}"):
        m = re.search(pat, text)
        if m:
            return re.sub(r"\\[a-zA-Z]+|[{}]", "", m.group(1)).strip()
    return main_tex.stem


def run(main_tex: Path, book_root: Path, work: Path,
        explicit_title: str | None = None) -> str:
    """Preprocess all chapters into work/epub_build/ and write
    work/epub_master.tex. Returns the detected/!given book title."""
    pre, body = split_preamble(main_tex)
    order = chapter_input_order(body)
    fig_index = _global_figure_index(book_root)
    chap_dir = _chapter_dir(book_root)
    out_dir = work / "epub_build"
    out_dir.mkdir(exist_ok=True)

    for ref in order:
        path = (book_root / ref)
        if path.suffix != ".tex":
            path = path.with_suffix(".tex")
        if not path.is_file():
            # also try the chapters/ dir
            alt = chap_dir / Path(ref).name
            alt = alt if alt.suffix == ".tex" else alt.with_suffix(".tex")
            if alt.is_file():
                path = alt
            else:
                continue
        txt = path.read_text(encoding="utf-8", errors="replace")
        if path.name in fig_index:
            txt = _replace_tikz(txt, fig_index[path.name])
        txt = mathfix.lift_math_labels(txt)
        txt = _anchor_float_labels(txt)
        txt = _convert_theorem_boxes(txt)
        txt = mathfix.fix(txt)
        (out_dir / path.name).write_text(txt, encoding="utf-8")

    # ---- master file --------------------------------------------------
    # keep only macro definitions from the preamble (pandoc reads these
    # for MathML); drop layout/font/package noise.
    macros = []
    for line in pre.splitlines():
        st = line.strip()
        if st.startswith(("\\newcommand", "\\renewcommand",
                           "\\DeclareMathOperator", "\\providecommand")):
            if any(x in st for x in ("usefont", "headrule", "footrule",
                                      "pagestyle", "thepage", "chaptername")):
                continue
            macros.append(line)

    body2 = re.sub(
        r"\\(?:input|include)\{([^}]+)\}",
        lambda m: f"\\input{{epub_build/{Path(m.group(1)).stem}}}",
        body)

    master = ("\\documentclass{book}\n"
              "\\usepackage{amsmath,amssymb,amsfonts,bm}\n"
              "\\usepackage{graphicx}\n"
              + "\n".join(macros) + "\n"
              + body2)
    (work / "epub_master.tex").write_text(master, encoding="utf-8")

    return _detect_title(main_tex, explicit_title)
