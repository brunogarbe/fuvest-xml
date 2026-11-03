---
name: verify-exam
description: Check an exam XML against the schema and its source PDF/images before it is promoted to exams/xml-verified/. Use when asked to verify, review or proofread an exam file.
---

# Verify an exam XML

Argument: path of a file in `exams/xml/`.

1. `uv run fuvest-xml-validate <file> --detailed` and fix schema errors (see `docs/format.md`).
2. Confirm option counts (5, or 4 for UNICAMP) and that question numbers are consecutive.
3. Check every `<image src>` exists under `images/`.
4. Compare the text with the source in `exams/pdf/` (read only the needed pages) and report differences
   in accents, math (`<m>`, `<math>` as LaTeX) and option order. Fix only clear transcription errors.
5. Run `uv run fuvest-xml-format <file>` and validate again.
6. Report what changed. Do NOT copy the file to `exams/xml-verified/`; the user does that after review.
