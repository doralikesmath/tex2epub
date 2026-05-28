#!/usr/bin/env python3
"""
tex2epub.py -- Convert a multi-file LaTeX book to a validated EPUB 3.

This is a generalised version of a pipeline built to convert a 567-page
quantitative-finance textbook (24 chapters, 8 appendices, ~5000 equations,
50 TikZ figures, ~120 code listings) into an EPUB that passes `epubcheck`
with zero errors and zero warnings, and whose equations render as native
MathML.

WHAT IT DOES
------------
  1. Extracts every `tikzpicture` into a standalone document, compiles each
     to PDF, and rasterises to PNG. (Pandoc cannot render TikZ directly.)
  2. Preprocesses the chapter sources:
       - replaces each tikzpicture with an \\includegraphics of its PNG
       - converts custom theorem-like environments (tcolorbox / amsthm)
         into a bold lead-in + blockquote that pandoc handles
       - moves \\label{} commands out of display-math (pandoc leaks them
         into the MathML annotation otherwise) and keeps them as anchors
       - rewrites math constructs pandoc's MathML reader rejects
         (\\Bigl/\\Bigr, &&, \\qed, \\hat\\bm, \\emph-in-math, {\\rm ..},
         booktabs rules inside a math array)
  3. Runs `pandoc` to EPUB 3 with --mathml, chapter-level splitting, a TOC,
     a cover image, and a stylesheet.
  4. Post-processes the EPUB to satisfy `epubcheck`:
       - strips invalid `displaystyle` attributes off non-math elements
       - strips invalid `label` attributes
       - sanitises `id`/`href` fragment values (no whitespace)
       - removes duplicate IDs
       - fixes empty/self-closing nav anchors
       - injects `dc:title` and the `mathml` manifest property where needed
  5. Numbers and rewrites cross-references so they read as "Eq. 5",
     "Listing 2", "Definition 7", chapter titles -- not raw `[eq:key]`.
  6. Repackages (mimetype stored first, uncompressed) and -- if epubcheck
     is installed -- validates.

REQUIREMENTS
------------
  - pandoc 3.x            (apt install pandoc      / brew install pandoc)
  - a LaTeX distribution  (TeX Live: pdflatex must be on PATH)
  - poppler-utils         (pdftoppm; apt install poppler-utils)
  - Python 3.9+
  - Pillow                (pip install pillow)              [for the cover]
  - epubcheck             (pip install epubcheck)  [optional, for --validate]

USAGE
-----
  python3 tex2epub.py main.tex
  python3 tex2epub.py main.tex --output mybook.epub --title "My Book" \\
                               --author "A. Writer" --validate

  main.tex is the LaTeX root file. It is expected to pull chapters in with
  \\input{...} or \\include{...}. The preamble between \\documentclass and
  \\begin{document} is reused for figure compilation and macro extraction.

NOTES & LIMITATIONS
-------------------
  - Pandoc does not carry LaTeX's chapter/equation numbering. This script
    re-numbers equations and listings sequentially *per chapter file*
    ("Eq. 5" within a chapter), which is unambiguous but not "5.3" form.
  - The theorem-box conversion is intentionally lossy: coloured tcolorbox
    styling becomes a uniform blockquote. Styling lives in the CSS instead.
  - It cannot verify MathML *renders* -- only that it is well-formed XML.
    Check the result in a MathML-capable reader (Apple Books, Thorium,
    Calibre, or KOReader on e-ink devices). The default reader on some
    e-ink tablets does NOT render MathML.
  - Tested against one large book; treat the math-fix list in
    `epub_lib/mathfix.py` as a starting point and extend it if pandoc
    reports "Could not convert TeX math" for a construct not handled here.

The heavy lifting is split into the `epub_lib/` package so each stage can
be read, tested, or reused on its own.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from epub_lib import (
    figures,
    preprocess,
    pandoc_run,
    postprocess,
    crossref,
    cover,
    validate,
)


_REQUIRED_TOOLS = {
    "pdflatex":  ("a LaTeX distribution (TeX Live, MiKTeX)",
                  "TeX Live:    sudo apt install texlive-full   "
                  "(Linux)\n"
                  "             brew install --cask mactex      "
                  "(macOS)\n"
                  "MiKTeX:      https://miktex.org/download     "
                  "(Windows)"),
    "pdftoppm":  ("poppler-utils (rasterises PDFs to PNG)",
                  "Linux (apt):  sudo apt install poppler-utils\n"
                  "Linux (dnf):  sudo dnf install poppler-utils\n"
                  "macOS:        brew install poppler\n"
                  "Windows:      https://github.com/oschwartz10612/"
                  "poppler-windows/releases"),
    "pandoc":    ("pandoc 3.x",
                  "Linux:        sudo apt install pandoc\n"
                  "macOS:        brew install pandoc\n"
                  "Windows:      https://pandoc.org/installing.html"),
}


def _check_external_tools() -> list[str]:
    """Return a list of missing tool names; empty list if all present."""
    import shutil as _sh
    missing = []
    for name in _REQUIRED_TOOLS:
        if _sh.which(name) is None:
            missing.append(name)
    return missing


def _print_missing_tools(missing: list[str]) -> None:
    print("\nerror: the following external tools are required but not "
          "found on your PATH:\n", file=sys.stderr)
    for name in missing:
        what, how = _REQUIRED_TOOLS[name]
        print(f"  - {name}  ({what})", file=sys.stderr)
        for line in how.splitlines():
            print(f"      {line}", file=sys.stderr)
        print(file=sys.stderr)
    print("After installing, run `<tool> --version` to confirm it works, "
          "then re-run tex2epub.py.", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Convert a multi-file LaTeX book to a validated EPUB 3.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("main_tex", help="LaTeX root file (e.g. main.tex)")
    ap.add_argument("-o", "--output", default="book.epub",
                    help="output EPUB filename")
    ap.add_argument("--title", default=None,
                    help="book title (default: read from \\title or pdftitle)")
    ap.add_argument("--author", default="", help="book author")
    ap.add_argument("--lang", default="en-US", help="BCP-47 language code")
    ap.add_argument("--workdir", default="_tex2epub_build",
                    help="scratch directory (created/overwritten)")
    ap.add_argument("--dpi", type=int, default=200,
                    help="rasterisation DPI for TikZ figures")
    ap.add_argument("--split-level", type=int, default=2,
                    help="pandoc heading level to split files at "
                         "(2 if chapters are level-2, e.g. under \\part)")
    ap.add_argument("--no-cover", action="store_true",
                    help="do not generate a cover image")
    ap.add_argument("--cover", default=None,
                    help="use this image file as the cover instead of "
                         "generating one")
    ap.add_argument("--validate", action="store_true",
                    help="run epubcheck on the result (needs the "
                         "`epubcheck` python package)")
    ap.add_argument("--highlight-style", default="pygments",
                    help="syntax-highlight style for code listings "
                         "(pygments, tango, espresso, zenburn, kate, "
                         "monochrome, breezedark, haddock). Run "
                         "`pandoc --list-highlight-styles` for the "
                         "full list. Pass 'none' to disable.")
    ap.add_argument("--keep-workdir", action="store_true",
                    help="do not delete the scratch directory at the end")
    args = ap.parse_args()

    main_tex = Path(args.main_tex).resolve()
    if not main_tex.is_file():
        print(f"error: {main_tex} not found", file=sys.stderr)
        return 2

    missing = _check_external_tools()
    if missing:
        _print_missing_tools(missing)
        return 3

    book_root = main_tex.parent
    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "img").mkdir()
    (work / "epub_build").mkdir()

    print("=" * 64)
    print(f"tex2epub  ::  {main_tex.name}  ->  {args.output}")
    print("=" * 64)

    # ---- 1. figures ----------------------------------------------------
    print("\n[1/6] Extracting and rendering TikZ figures ...")
    n_figs = figures.render_all(main_tex, book_root, work, dpi=args.dpi)
    print(f"      {n_figs} figure(s) rendered to PNG.")

    # ---- 2. preprocess -------------------------------------------------
    print("\n[2/6] Preprocessing LaTeX sources ...")
    title = preprocess.run(main_tex, book_root, work,
                           explicit_title=args.title)
    print(f"      title: {title}")

    # ---- cover ---------------------------------------------------------
    cover_path = None
    if args.cover:
        cover_path = Path(args.cover).resolve()
    elif not args.no_cover:
        cover_path = work / "cover.png"
        cover.generate(title, args.author, cover_path)
        print(f"      cover image generated.")

    # ---- 3. pandoc -----------------------------------------------------
    print("\n[3/6] Running pandoc (LaTeX -> EPUB 3, MathML) ...")
    epub_tmp = work / "_pandoc_out.epub"
    hl = None if args.highlight_style.lower() == "none" else args.highlight_style
    n_mathwarn = pandoc_run.run(
        work=work, output=epub_tmp, title=title, author=args.author,
        lang=args.lang, split_level=args.split_level, cover=cover_path,
        highlight_style=hl,
    )
    if n_mathwarn:
        print(f"      WARNING: {n_mathwarn} equation(s) failed MathML "
              f"conversion and will show as raw TeX.")
        print(f"      -> extend epub_lib/mathfix.py to handle them.")
    else:
        print("      all equations converted to MathML.")

    # ---- 4. postprocess (epubcheck fixes) ------------------------------
    print("\n[4/6] Post-processing EPUB for epubcheck compliance ...")
    extracted = work / "_epub"
    postprocess.run(epub_tmp, extracted, title=title)

    # ---- 5. cross-references -------------------------------------------
    print("\n[5/6] Numbering and rewriting cross-references ...")
    stats = crossref.run(extracted)
    for kind, n in stats.items():
        print(f"      {kind}: {n} reference(s) rewritten")

    # ---- 6. repackage --------------------------------------------------
    print("\n[6/6] Repackaging EPUB ...")
    out = Path(args.output).resolve()
    postprocess.repackage(extracted, out)
    size_kb = out.stat().st_size // 1024
    print(f"      written: {out}  ({size_kb} KB)")

    # ---- optional validation ------------------------------------------
    if args.validate:
        print("\n[+]   Validating with epubcheck ...")
        ok, n_err, n_warn = validate.run(out)
        print(f"      valid={ok}  errors={n_err}  warnings={n_warn}")
        if not ok:
            print("      (see messages above; fix and re-run)")

    if not args.keep_workdir:
        shutil.rmtree(work)
    else:
        print(f"\nscratch directory kept at: {work}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
