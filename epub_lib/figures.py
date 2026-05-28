"""epub_lib.figures -- turn every TikZ picture into a PNG.

Pandoc cannot render TikZ. We extract each `tikzpicture`, wrap it in a
`standalone` document that reuses the book's macros/colours/libraries,
compile with pdflatex, and rasterise with pdftoppm.

Figures are numbered globally in *sorted chapter-filename order* so that
`preprocess.py` can substitute them back deterministically.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .common import split_preamble


def _figure_preamble(main_tex: Path) -> str:
    r"""Build a `standalone`-class preamble for compiling figures.

    A figure only needs: graphics/plotting packages, their setup, colours,
    and math macros. We keep exactly those lines and skip everything else
    (theorem-box definitions, listings setup, layout, fonts) -- carrying
    those over would pull in dropped packages and dump raw text onto the
    figure.
    """
    pre, _ = split_preamble(main_tex)

    # packages a figure may legitimately need
    fig_packages = {
        "tikz", "pgfplots", "pgf", "amsmath", "amssymb", "amsfonts",
        "bm", "xcolor", "graphicx", "mathtools", "siunitx",
    }
    keep_pkg_lines: list[str] = []
    keep_setup_lines: list[str] = []

    for line in pre.splitlines():
        st = line.strip()
        if st.startswith("\\usepackage"):
            inside = st[st.find("{") + 1: st.rfind("}")] if "{" in st else ""
            pkgs = {p.strip() for p in inside.split(",")}
            wanted = pkgs & fig_packages
            if wanted:
                keep_pkg_lines.append("\\usepackage{"
                                      + ",".join(sorted(wanted)) + "}")
        elif st.startswith((
                "\\usetikzlibrary", "\\pgfplotsset", "\\definecolor",
                "\\colorlet", "\\DeclareMathOperator", "\\pgfplotscreateplotcyclelist")):
            keep_setup_lines.append(line)
        elif st.startswith(("\\newcommand", "\\renewcommand",
                             "\\providecommand")):
            # keep only short math macros; skip layout/font/box redefs
            if any(x in st for x in (
                    "headrule", "footrule", "pagestyle", "thepage",
                    "chaptername", "usefont", "tcb", "lst", "title")):
                continue
            keep_setup_lines.append(line)

    return (
        "\\documentclass[border=4pt]{standalone}\n"
        "\\usepackage{amsmath,amssymb,amsfonts,bm}\n"
        "\\usepackage{tikz}\n"
        "\\usepackage{pgfplots}\n"
        + "\n".join(keep_pkg_lines) + "\n"
        + "\n".join(keep_setup_lines) + "\n"
    )


def _all_tikz(book_root: Path) -> list[str]:
    """Every tikzpicture across chapters/, in sorted-filename then in-file
    order. Looks in the directory holding the chapter files."""
    chap_dir = _locate_chapter_dir(book_root)
    figs: list[str] = []
    for f in sorted(chap_dir.glob("*.tex")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        figs += re.findall(
            r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", txt, re.DOTALL)
    return figs


def _locate_chapter_dir(book_root: Path) -> Path:
    """Pick the directory that actually holds the chapter files: prefer a
    `chapters/` subdirectory, else whichever candidate has the most .tex
    files (so a root dir containing only main.tex is not chosen)."""
    candidates = [book_root / "chapters", book_root]
    best = book_root
    best_n = -1
    for d in candidates:
        if d.is_dir():
            n = len(list(d.glob("*.tex")))
            if n > best_n:
                best, best_n = d, n
    return best


def render_all(main_tex: Path, book_root: Path, work: Path,
               dpi: int = 200) -> int:
    """Render every TikZ picture to work/img/figNN.png. Returns the count."""
    figs = _all_tikz(book_root)
    if not figs:
        return 0

    preamble = _figure_preamble(main_tex)
    figsrc = work / "figsrc"
    figsrc.mkdir(exist_ok=True)
    imgdir = work / "img"
    imgdir.mkdir(exist_ok=True)

    for i, tk in enumerate(figs):
        doc = preamble + "\\begin{document}\n" + tk + "\n\\end{document}\n"
        (figsrc / f"fig{i:02d}.tex").write_text(doc, encoding="utf-8")

    for i in range(len(figs)):
        name = f"fig{i:02d}"
        # compile (run twice in case the figure has internal references)
        for _ in range(2):
            try:
                subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", f"{name}.tex"],
                    cwd=figsrc, capture_output=True, check=False)
            except FileNotFoundError:
                raise RuntimeError(
                    "pdflatex not found. Install a LaTeX distribution "
                    "(TeX Live / MiKTeX) and make sure 'pdflatex' is on "
                    "your PATH.")
        pdf = figsrc / f"{name}.pdf"
        if not pdf.is_file():
            raise RuntimeError(
                f"figure {name} failed to compile -- inspect "
                f"{figsrc/name}.log for the LaTeX error.")
        # rasterise
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi), "-singlefile",
                 f"{name}.pdf", str(imgdir / name)],
                cwd=figsrc, capture_output=True, check=False)
        except FileNotFoundError:
            raise RuntimeError(
                "pdftoppm not found. Install poppler-utils:\n"
                "  Linux: sudo apt install poppler-utils\n"
                "  macOS: brew install poppler\n"
                "  Windows: https://github.com/oschwartz10612/"
                "poppler-windows/releases\n"
                "After installing, run `pdftoppm -v` to confirm, "
                "then re-run tex2epub.py.")

    return len(figs)
