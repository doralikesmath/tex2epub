"""epub_lib.postprocess -- make the EPUB pass epubcheck, then repackage.

Pandoc's EPUB output triggers several epubcheck errors on math-heavy books.
Each fix here corresponds to a real error class observed in practice:

  * `displaystyle` / `scriptlevel` attributes on elements other than
    <math>/<mstyle>            -> stripped
  * stray `label="..."` attributes (from \\label leaking onto <pre> etc.)
                               -> stripped
  * whitespace in id/href fragment values (LaTeX labels with spaces)
                               -> hyphenated
  * duplicate IDs (same label anchored twice)   -> later ones dropped
  * empty / self-closing <a> in the nav         -> given placeholder text
  * missing <dc:title> in the OPF               -> inserted
  * a <math> element living in nav.xhtml without the manifest `mathml`
    property                   -> property added
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .common import sanitize_id


def _extract(epub: Path, dest: Path) -> None:
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(epub) as z:
        z.extractall(dest)


def _xhtml_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.xhtml"))


def _strip_bad_math_attrs(s: str) -> str:
    """Remove displaystyle/scriptlevel from any element except math/mstyle."""
    def fix(m: re.Match) -> str:
        tag = m.group(0)
        name = re.match(r"<(\w+)", tag).group(1)
        if name in ("math", "mstyle"):
            return tag
        tag = re.sub(r'\s+displaystyle="[^"]*"', "", tag)
        tag = re.sub(r'\s+scriptlevel="[^"]*"', "", tag)
        return tag
    return re.sub(r"<m[a-z]+[^>]*>", fix, s)


def _strip_label_attrs(s: str) -> str:
    for _ in range(2):                      # an element may carry it twice
        s = re.sub(r'(<[a-zA-Z][a-zA-Z0-9]*\b[^>]*?)\s+label="[^"]*"',
                   r"\1", s)
    return s


def _sanitize_ids(s: str) -> str:
    s = re.sub(r'\bid="([^"]*)"',
               lambda m: f'id="{sanitize_id(m.group(1))}"', s)
    s = re.sub(r'href="([^"#]*)#([^"]*)"',
               lambda m: f'href="{m.group(1)}#{sanitize_id(m.group(2))}"', s)
    return s


def _dedupe_ids(root: Path) -> None:
    """If the same id occurs more than once across the book, keep the first
    and strip the attribute from later occurrences."""
    seen: set[str] = set()
    for f in _xhtml_files(root):
        s = f.read_text(encoding="utf-8")
        out = []
        last = 0
        for m in re.finditer(r'\bid="([^"]*)"', s):
            val = m.group(1)
            if val in seen:
                out.append(s[last:m.start()])
                last = m.end()             # drop this id="..."
            else:
                seen.add(val)
        out.append(s[last:])
        new = "".join(out)
        if new != s:
            f.write_text(new, encoding="utf-8")


def _fix_nav(nav: Path) -> None:
    if not nav.is_file():
        return
    s = nav.read_text(encoding="utf-8")
    nbsp = "\u00a0"
    # self-closing or empty anchors are invalid in nav
    s = re.sub(r"<a ([^>]*?)\s*/>",
               lambda m: f"<a {m.group(1)}>{nbsp}</a>", s)
    s = re.sub(r"<a([^>]*)>\s*</a>",
               lambda m: f"<a{m.group(1)}>{nbsp}</a>", s)
    nav.write_text(s, encoding="utf-8")


def _fix_opf(opf: Path, nav: Path, title: str = "Untitled") -> None:
    if not opf.is_file():
        return
    s = opf.read_text(encoding="utf-8")
    if "<dc:title" not in s:
        s = s.replace(
            'xmlns:opf="http://www.idpf.org/2007/opf">',
            'xmlns:opf="http://www.idpf.org/2007/opf">\n'
            f'<dc:title id="epub-title-1">{title}</dc:title>\n'
            '<meta refines="#epub-title-1" '
            'property="title-type">main</meta>', 1)
    # if the nav contains MathML, the manifest item needs the property
    if nav.is_file() and "<math" in nav.read_text(encoding="utf-8"):
        s = s.replace('properties="nav" />', 'properties="nav mathml" />')
        s = s.replace('properties="nav"/>', 'properties="nav mathml"/>')
    opf.write_text(s, encoding="utf-8")


def run(epub_tmp: Path, extracted: Path, title: str = "Untitled") -> None:
    """Extract `epub_tmp` into `extracted` and apply all compliance fixes."""
    _extract(epub_tmp, extracted)

    text_files = _xhtml_files(extracted)
    for f in text_files:
        s = f.read_text(encoding="utf-8")
        o = s
        s = _strip_bad_math_attrs(s)
        s = _strip_label_attrs(s)
        s = _sanitize_ids(s)
        if s != o:
            f.write_text(s, encoding="utf-8")

    # opf / ncx also carry id/href values
    for f in extracted.rglob("*.opf"):
        f.write_text(_sanitize_ids(f.read_text(encoding="utf-8")),
                     encoding="utf-8")
    for f in extracted.rglob("*.ncx"):
        f.write_text(_sanitize_ids(f.read_text(encoding="utf-8")),
                     encoding="utf-8")

    _dedupe_ids(extracted)

    nav = next(iter(extracted.rglob("nav.xhtml")), None)
    opf = next(iter(extracted.rglob("*.opf")), None)
    if nav:
        _fix_nav(nav)
    if opf:
        _fix_opf(opf, nav if nav else Path("/nonexistent"), title)


def repackage(extracted: Path, output: Path) -> None:
    """Zip `extracted` into a valid EPUB: the `mimetype` entry must be
    first and stored (uncompressed)."""
    if output.exists():
        output.unlink()
    # locate the EPUB root (the dir containing 'mimetype')
    mimetype = next(iter(extracted.rglob("mimetype")), None)
    if mimetype is None:
        raise RuntimeError("no mimetype file found in extracted EPUB")
    root = mimetype.parent

    with zipfile.ZipFile(output, "w") as z:
        # mimetype first, stored
        z.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for p in sorted(root.rglob("*")):
            if p == mimetype or p.is_dir():
                continue
            z.write(p, str(p.relative_to(root)),
                    compress_type=zipfile.ZIP_DEFLATED)
