"""epub_lib.pandoc_run -- invoke pandoc, count math-conversion failures."""
from __future__ import annotations

import subprocess
from pathlib import Path

# A compact stylesheet: equations centred and scrollable, code boxed,
# figures centred, theorem-boxes as a tinted blockquote.
_CSS = """\
body { line-height: 1.5; }
h1 { color: #0f3764; page-break-before: always; }
h2, h3 { color: #1e5aa0; }

math[display="block"] {
  display: block; margin: 0.8em auto; overflow-x: auto; max-width: 100%;
}

pre {
  background: #f8f8f8; border: 1px solid #c8c8c8; border-radius: 3px;
  padding: 0.6em 0.8em; font-size: 0.82em; line-height: 1.35;
  white-space: pre-wrap; word-wrap: break-word;
  /* allow a long listing to flow across a page break instead of being
     clipped. NO overflow:auto / overflow:hidden here -- on many e-readers
     that turns the block into a one-page scroll box and drops everything
     past the page break. */
  overflow: visible;
  page-break-inside: auto; break-inside: auto;
}
code { font-family: "DejaVu Sans Mono", monospace; }
p code { background: #f0f0f0; padding: 0 2px; border-radius: 2px; }

/* Override pandoc's skylighting rules so highlighted code (a) wraps
   instead of overflowing the narrow page of an e-reader, and (b) breaks
   across pages instead of being clipped to one. Pandoc injects its own
   `pre > code.sourceCode { white-space: pre }`, an `overflow` setting,
   and a line-number indent (`text-indent: -5em; padding-left: 5em`) into
   each chapter's <head>; those selectors are specific enough to win, so
   we match them. */
pre.sourceCode,
div.sourceCode {
  background: #f8f8f8; border: 1px solid #c8c8c8; border-radius: 3px;
  padding: 0.6em 0.8em;
  overflow: visible !important;
  page-break-inside: auto; break-inside: auto;
}
pre > code.sourceCode {
  white-space: pre-wrap !important;
  word-break: break-word; overflow-wrap: anywhere;
  overflow: visible !important;
  font-size: 0.82em; line-height: 1.35;
  page-break-inside: auto; break-inside: auto;
}
pre > code.sourceCode > span {
  /* cancel the hanging-indent pandoc uses for line numbers, which on a
     narrow screen pushes wrapped text off the left edge */
  text-indent: 0 !important; padding-left: 0 !important;
  display: inline; line-height: 1.35;
}
/* hide the per-line number backlinks (the leading 1,2,3 gutter) -- they
   don't reflow well on e-ink and waste horizontal space */
pre > code.sourceCode > span > a:first-child { display: none; }

img { max-width: 100%; height: auto; display: block; margin: 0.8em auto; }
figure { margin: 1em 0; text-align: center; }
figcaption { font-size: 0.85em; color: #444; font-style: italic; }

blockquote {
  margin: 0.8em 0; padding: 0.5em 0.9em;
  border-left: 3px solid #1e5aa0; background: #f4f8ff;
}
p > strong:first-child { color: #0f3764; }

table { border-collapse: collapse; margin: 0.8em auto; font-size: 0.9em; }
th, td { border: 1px solid #bbb; padding: 3px 8px; }
th { background: #eef2f8; }
"""


def run(work: Path, output: Path, title: str, author: str, lang: str,
        split_level: int, cover: Path | None,
        highlight_style: str | None = "pygments") -> int:
    """Run pandoc. Returns the number of 'Could not convert TeX math'
    warnings (0 means every equation became MathML).

    ``highlight_style`` is passed straight to pandoc's
    ``--highlight-style``. Pass ``None`` to disable syntax highlighting.
    Valid built-in styles include: pygments, tango, espresso, zenburn,
    kate, monochrome, breezedark, haddock (run ``pandoc
    --list-highlight-styles`` for the current list).
    """
    css = work / "epub_style.css"
    css.write_text(_CSS, encoding="utf-8")

    meta = work / "epub_meta.yaml"
    meta.write_text(
        "---\n"
        f'title: "{title}"\n'
        f'author: "{author}"\n'
        f"lang: {lang}\n"
        "...\n", encoding="utf-8")

    cmd = [
        "pandoc",
        str(work / "epub_master.tex"),
        str(meta),
        "-f", "latex",
        "-t", "epub3",
        "--mathml",
        "--toc", "--toc-depth=3",
        f"--split-level={split_level}",
        f"--css={css}",
        f"--resource-path=.:{work}:{work / 'epub_build'}",
        "-o", str(output),
    ]
    if highlight_style:
        cmd.append(f"--highlight-style={highlight_style}")
    else:
        cmd.append("--no-highlight")
    if cover and Path(cover).is_file():
        cmd.append(f"--epub-cover-image={cover}")

    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            "pandoc not found. Install pandoc 3.x:\n"
            "  Linux: sudo apt install pandoc\n"
            "  macOS: brew install pandoc\n"
            "  Windows: https://pandoc.org/installing.html")
    if proc.returncode != 0:
        raise RuntimeError("pandoc failed:\n" + proc.stderr)

    return proc.stderr.count("Could not convert TeX math")
