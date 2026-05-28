"""epub_lib -- staged helpers for the tex2epub pipeline.

Each module is one stage and can be imported and used on its own:

    figures      extract tikzpictures, compile to PDF, rasterise to PNG
    mathfix      rewrite math constructs pandoc's MathML reader rejects
    preprocess   substitute figures, convert theorem boxes, build master.tex
    cover        generate a simple cover image
    pandoc_run   invoke pandoc with the right flags
    postprocess  fix the EPUB so epubcheck passes; repackage
    crossref     number and rewrite [eq:..], [lst:..], [chap:..] references
    validate     run epubcheck (optional)
"""
