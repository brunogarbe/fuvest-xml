---
name: new-exam
description: Convert a new exam PDF into XML. Use when asked to add or import an exam from a PDF.
---

# Add a new exam from a PDF

1. Place the PDF under `exams/pdf/` (local only, gitignored). Name: `<exam>_<year>_fase_NN[_dia_NN|_<subject>].pdf`.
2. `uv run fuvest-xml-read-pdfs` (skips XML that already exists).
3. Validate with `uv run fuvest-xml-validate exams/xml/<name>.xml --detailed` and fix errors using `docs/format.md`
   and `docs/classifications.md`.
4. Extracted figures go to `images/<exam>/<year>/<phase>/`; reference them with `src` relative to `images/`.
5. Run `fuvest-xml-format`, validate again, and hand over for human review (see the `verify-exam` skill).
