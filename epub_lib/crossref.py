"""epub_lib.crossref -- number and rewrite cross-references.

Pandoc does not carry LaTeX's chapter/equation numbering, so a `\\ref{eq:x}`
ends up as a link whose visible text is the raw key, e.g. "[eq:se_mean]".
This module:

  * numbers equations and listings sequentially *per chapter file*
  * rewrites each reference link's visible text to a clean label
    ("Eq. 5", "Listing 2", "Definition 7", or a chapter title)
  * removes the duplicated lead-in word: LaTeX source typically writes
    "Chapter~\\ref{..}" / "Eq.~\\eqref{..}", so the link text must NOT
    repeat that word -- otherwise the reader sees "Chapter Chapter 3".

It is deliberately conservative: a reference whose anchor cannot be found
is left untouched rather than guessed at.
"""
from __future__ import annotations

import re
from pathlib import Path

NBSP = "\u00a0"

# theorem-ish prefixes -> display word
_BOX_WORD = {
    "def": "Definition", "thm": "Theorem", "prop": "Proposition",
    "lem": "Lemma", "cor": "Corollary", "ex": "Example",
    "rem": "Remark", "warn": "Warning", "shap": "SHAP Insight",
    "nlp": "NLP Insight", "llm": "LLM Application",
}


def _xhtml(root: Path) -> list[Path]:
    # only the reading-order text documents
    return sorted(root.rglob("*.xhtml"))


def _number_anchors(s: str, prefix: str,
                    require_block_math: bool) -> dict[str, int]:
    """Return {key: N} for anchors whose id starts with `prefix:` in this
    file, numbered in document order."""
    out: dict[str, int] = {}
    i = 0
    if require_block_math:
        # equation: a <span/div id="eq:.."> immediately before block math
        pat = re.compile(
            r'<(?:span|div) id="(' + prefix + r':[^"]+)"[^>]*>'
            r'(?:</(?:span|div)>)?\s*(?:<p>)?\s*<math display="block"')
    else:
        pat = re.compile(r'id="(' + prefix + r':[^"]+)"')
    for m in pat.finditer(s):
        i += 1
        out[m.group(1)] = i
    return out


def run(extracted: Path) -> dict[str, int]:
    """Rewrite all cross-reference link texts. Returns a small stats dict."""
    files = _xhtml(extracted)
    stats = {"equations": 0, "listings": 0, "theorem-boxes": 0,
             "chapters": 0}

    # ---- per-file numbering -------------------------------------------
    eqnum: dict[str, str] = {}
    lstnum: dict[str, str] = {}
    boxnum: dict[str, str] = {}
    chaptitle: dict[str, str] = {}

    for f in files:
        s = f.read_text(encoding="utf-8")

        # equations: number any eq: anchor in document order
        i = 0
        for m in re.finditer(r'id="(eq:[^"]+)"', s):
            i += 1
            eqnum[m.group(1)] = str(i)

        # listings
        i = 0
        for m in re.finditer(r'id="(lst:[^"]+)"', s):
            i += 1
            lstnum[m.group(1)] = str(i)

        # theorem-like boxes: number per type per file
        counters: dict[str, int] = {}
        for m in re.finditer(
                r'id="((?:' + "|".join(_BOX_WORD) + r'):[^"]+)"', s):
            key = m.group(1)
            typ = key.split(":")[0]
            counters[typ] = counters.get(typ, 0) + 1
            boxnum[key] = str(counters[typ])

        # chapter titles: first heading in the file applies to every
        # chap: anchor that lives in it
        h = re.search(r"<h[12][^>]*>(.*?)</h[12]>", s, re.DOTALL)
        if h:
            title = re.sub(r"<[^>]+>", "", h.group(1)).strip()
            for m in re.finditer(r'id="(chap:[^"]+)"', s):
                chaptitle.setdefault(m.group(1), title)

    # ---- rewrite links -------------------------------------------------
    def rewrite(s: str, prefix: str, numbering: dict[str, str],
                word: str) -> tuple[str, int]:
        """Rewrite <a ...#prefix:key...>TEXT</a>.

        The link text becomes just the number (e.g. "5"); the lead-in
        word is assumed to be in the surrounding prose. The exception is
        a reference with no lead-in word -- handled by `_ensure_word`.
        """
        count = [0]

        def repl(m: re.Match) -> str:
            full, key = m.group(0), m.group(1)
            if key not in numbering:
                return full
            count[0] += 1
            return re.sub(r">[^<>]*</a>", f">{numbering[key]}</a>", full)

        s = re.sub(
            r'<a href="[^"]*#(' + prefix + r':[^"]+)"[^>]*>[^<>]*</a>',
            repl, s)
        return s, count[0]

    for f in files:
        s = f.read_text(encoding="utf-8")
        o = s

        s, n = rewrite(s, "eq", eqnum, "Eq.")
        stats["equations"] += n
        s, n = rewrite(s, "lst", lstnum, "Listing")
        stats["listings"] += n
        for pfx in _BOX_WORD:
            s, n = rewrite(s, pfx, boxnum, _BOX_WORD[pfx])
            stats["theorem-boxes"] += n

        # chapters: use the title, not a number
        def chap_repl(m: re.Match) -> str:
            full, key = m.group(0), m.group(1)
            if key not in chaptitle:
                return full
            stats["chapters"] += 1
            short = chaptitle[key].split(":")[0].strip()
            return re.sub(r">[^<>]*</a>",
                          f">\u201c{short}\u201d</a>", full)

        s = re.sub(r'<a href="[^"]*#(chap:[^"]+)"[^>]*>[^<>]*</a>',
                   chap_repl, s)

        # ---- de-duplicate lead-in words --------------------------------
        # "Eq. <a>5</a>"  is fine; the prose word stays.
        # but our chapter links carry only the title, so "Chapter X" is OK.
        # Guard against "<Word> <Word>" doublings if the link text still
        # carried the word for some reason:
        for w in ("Equation", "Eq\\.", "Listing", "Definition", "Theorem",
                  "Proposition", "Example", "Remark", "Warning", "Chapter"):
            s = re.sub(rf"\b({w})(?:{NBSP}|\s)+(\1)\b", r"\1", s)

        if s != o:
            f.write_text(s, encoding="utf-8")

    return stats
