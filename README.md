# tex2epub

Convert a multi-file LaTeX book to a validated EPUB 3 with native MathML
equations and properly rendered TikZ / pgfplots figures.

This is a generalised version of a pipeline built to convert a 567-page
quantitative-finance textbook (24 chapters, 8 appendices, ~5,000 equations,
50 TikZ figures, ~120 code listings) into an EPUB that passes `epubcheck`
with zero errors and zero warnings.

## Quick start

```bash
# basic
python3 tex2epub.py path/to/main.tex

# with title/author/validation
python3 tex2epub.py main.tex \
    --output mybook.epub \
    --title "My Book Title" \
    --author "Jane Author" \
    --validate

# pick a syntax-highlight theme (default: pygments), or turn it off
python3 tex2epub.py main.tex --highlight-style breezedark
python3 tex2epub.py main.tex --highlight-style none
```

## Syntax highlighting

Code listings are syntax-highlighted automatically. Because pandoc does
**not** read `\lstset` / `\lstdefinestyle`, the pipeline detects the book's
default `listings` language (e.g. from `\lstset{style=python}` →
`\lstdefinestyle{python}{language=Python}`) and injects `language=...` into
every `\begin{lstlisting}[...]` block that lacks one. Pandoc's skylighting
library then emits coloured `<span>`s and the colour rules are embedded in
each chapter file.

Choose a theme with `--highlight-style` (default `pygments`). Built-in
options: `pygments`, `tango`, `espresso`, `zenburn`, `kate`, `monochrome`,
`breezedark`, `haddock` (run `pandoc --list-highlight-styles` for the live
list). Pass `none` to disable highlighting. A block that already declares
its own language (say a `bash` snippet in a Python book) is left untouched.

## Requirements

The script calls three external tools. Install them first.

### pandoc 3.x

```
Linux:    sudo apt install pandoc
macOS:    brew install pandoc
Windows:  https://pandoc.org/installing.html
```

### A LaTeX distribution (provides `pdflatex`)

```
Linux:    sudo apt install texlive-full
macOS:    brew install --cask mactex
Windows:  https://miktex.org/download
```

(For Linux, `texlive-latex-extra texlive-fonts-extra texlive-pictures
texlive-science` is a leaner alternative if you don't want the full
distribution.)

### poppler-utils (provides `pdftoppm`)

```
Linux (apt):  sudo apt install poppler-utils
Linux (dnf):  sudo dnf install poppler-utils
macOS:        brew install poppler
Windows:      https://github.com/oschwartz10612/poppler-windows/releases
              (unzip and add bin/ to PATH)
```

### Python

Python 3.9 or later, with Pillow for cover generation:

```
pip install pillow
```

Optional: `pip install epubcheck` if you want to use the `--validate` flag.

### Verify the tools are visible

```
pandoc --version
pdflatex --version
pdftoppm -v
```

If any of those errors out, `tex2epub.py` will also fail. The script
checks all three at startup and prints install instructions if any are
missing.

## What it does (one stage per `epub_lib/` module)

| Stage | Module | What happens |
|------:|:-------|:-------------|
| 1 | `figures.py` | Extract every `tikzpicture`, wrap each in a `standalone` document carrying only figure-relevant packages (tikz, pgfplots, colours, math macros), compile with `pdflatex`, rasterise to PNG. |
| 2 | `preprocess.py` + `mathfix.py` | Substitute the rendered figures back; convert theorem-like `tcolorbox` environments to a bold lead-in + blockquote pandoc handles; lift `\label{}` out of display-math; inject `language=...` into `lstlisting` blocks for syntax highlighting; rewrite math constructs pandoc's MathML reader rejects (`\Bigl`/`\Bigr`, `&&` inside `aligned`, `\qed`, accented bold macros, `\emph` inside `\text{}`, booktabs rules inside math arrays, etc.). |
| 3 | `pandoc_run.py` | Run pandoc with `--mathml`, chapter-level splitting, TOC, cover, CSS. |
| 4 | `postprocess.py` | Fix everything `epubcheck` would complain about: invalid `displaystyle` attributes, stray `label=` attributes, whitespace in `id`/`href` values, duplicate IDs, empty nav anchors, missing `dc:title`, missing `mathml` manifest property. |
| 5 | `crossref.py` | Number equations and listings per chapter and rewrite link text so `\ref{eq:foo}` reads as `Eq. 5` instead of `[eq:foo]`; same for listings, theorem-boxes, chapter references. |
| 6 | `postprocess.repackage()` | Re-zip with `mimetype` first (stored, uncompressed). |

## Tested compatibility

- The default reader on some e-ink tablets (e.g. Boox NeoReader) does
  **not** render MathML. Use a MathML-capable reader: Apple Books,
  Thorium, Calibre's viewer, KOReader (free, e-ink-optimised, available
  via Google Play), or PocketBook reader.
- This tool *generates* valid MathML; it cannot test how a reader
  *renders* it.

## Extending the math-fix list

Pandoc's TeX→MathML reader is stricter than LaTeX. If pandoc reports
"Could not convert TeX math ..." for a construct not handled here, add a
rule to `epub_lib/mathfix.py`. The existing rules show the pattern.

## Caveats and known limitations

- Pandoc does not carry LaTeX's chapter/equation numbering. References
  are re-numbered sequentially *per chapter file*, so `Eq. 5` is the
  fifth display equation in that chapter, not "5.3" form.
- The theorem-box conversion is deliberately lossy: the coloured
  `tcolorbox` becomes a uniform blockquote. Differential styling
  (warning red, definition blue, etc.) would have to be added by tagging
  the blocks with classes during preprocessing — the current CSS treats
  every box the same.
- The `figures.py` module assumes a `chapters/` subdirectory (or that
  chapter `.tex` files sit next to `main.tex`). Pulling in chapters from
  arbitrarily nested directories may need adjustment of `_locate_chapter_dir`.
- The pipeline is for *books* — it expects `\input{...}` or
  `\include{...}` to pull in chapters, not a single monolithic source.

## Layout

```
tex2epub/
├── README.md              this file
├── tex2epub.py            entry point
└── epub_lib/
    ├── __init__.py
    ├── common.py          shared helpers + theorem-env table
    ├── figures.py         tikz/pgfplots -> PNG
    ├── mathfix.py         pandoc-MathML-compatible math rewrites
    ├── preprocess.py      build epub_master.tex
    ├── cover.py           generate a cover image
    ├── pandoc_run.py      invoke pandoc
    ├── postprocess.py     epubcheck-compliance fixes + repackage
    ├── crossref.py        number and rewrite cross-references
    └── validate.py        optional epubcheck pass
```

## License

This script bundle has no license header attached. Adapt it for your own
projects as you see fit.
