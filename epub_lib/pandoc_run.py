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
  overflow-x: auto; white-space: pre-wrap; word-wrap: break-word;
}
code { font-family: "DejaVu Sans Mono", monospace; }
p code { background: #f0f0f0; padding: 0 2px; border-radius: 2px; }

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
        split_level: int, cover: Path | None) -> int:
    """Run pandoc. Returns the number of 'Could not convert TeX math'
    warnings (0 means every equation became MathML)."""
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
