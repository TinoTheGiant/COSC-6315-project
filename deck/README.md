# Midterm deck

`midterm-deck.pptx` is built by `build-deck.js`, which is a pptxgenjs script:

    node build-deck.js

It needs `arch.png` beside it, which is the architecture figure rendered from
the TikZ source in `paper/sections/03-system-model.tex`.

The deck is built as a structured deck rather than hand-placed boxes: one
theme, named layouts, placeholders and sections. Changing a colour or a font
means changing `THEME` at the top of the script and rebuilding, not editing
fourteen slides.

Fonts are Cambria for headings and Calibri for body. Both are on the safe list,
which means the rendered checks on the slides are accurate rather than guessing
at substituted font widths.

Every number on a slide comes from `results/recorded/*.csv`, and the combined
cost figures come from `scripts/score_objective.py`. Each slide carries one
"In plain terms" line, and the detail lives in the speaker notes so the slides
stay sparse.

`archive/deck-v1-2026-10-20.pptx` is the previous deck, kept for reference.
