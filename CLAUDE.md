# fuvest-xml

Python (uv, Typer CLIs) tooling plus a corpus of Brazilian entrance exams (Fuvest, Enem, ITA, Unicamp,
Unesp, Fatec) encoded as XML validated by `xsd/fuvest_xml.xsd`. XML converts to LaTeX/HTML and indexes into SQLite.

## Pipeline

`exams/pdf/` (local only) -> `fuvest-xml-read-pdfs` -> `exams/xml/` (raw, unreviewed)
-> human review -> `exams/xml-verified/` (trusted) -> `fuvest-xml` (LaTeX/HTML) / `fuvest-xml-db` (SQLite)

## Commands

```bash
uv sync                                          # install
uv run fuvest-xml-validate exams/xml/FILE.xml    # validate (add --detailed for context; accepts globs)
uv run fuvest-xml-format exams/xml/FILE.xml      # pretty-print in place
uv run fuvest-xml exams/xml-verified/FILE.xml --html   # convert (omit --html for LaTeX)
```

There are no tests or linter yet. Validation is the check: run it after every XML edit.

## Layout

- `src/fuvest_xml/` - the package: `convert.py` (current converter), `convert_xml.py` (legacy, avoid),
  `validate.py`, `pretty_print.py`, `read_pdfs.py`, `database.py`, `gui.py` (PyQt5).
- `src/old/` - abandoned experiments. Ignore; do not edit or import.
- `xsd/fuvest_xml.xsd` - the schema (source of truth). `css/`, `styles/` - HTML/LaTeX styling.
- `images/<exam>/<year>/<phase>/` - figures; XML `<image src>` is relative to `images/`.
- `exams/xml/` raw, `exams/xml-verified/` reviewed. Files are named `<exam>_<year>_fase_NN[_dia_NN|_<subject>].xml`.
- `output/`, `exams/pdf/`, `exams/provas/` - generated or local-only (gitignored). Do not read them; large binaries.

## Rules

- Never modify `exams/xml-verified/` unless asked; those files were checked by hand.
- Do not read all of `exams/xml/` (385 files). Open the one file you need, or use Grep.
- XML style: UTF-8, tab indentation, Portuguese text kept verbatim (accents included), `lang="pt-br"`.
  Run `fuvest-xml-format` after structural edits.
- Math/chemistry go in `<m>`, `<math>`, `<c>`, `<chem>` as LaTeX, never Unicode approximations.
- Objective questions need 5 options (4 for UNICAMP). `is_correct` is required on each; answer keys are not always filled in, so do not assume one `true` per question.
- Schema changes: edit the XSD, then check that `exams/xml-verified/*.xml` still validate, and update `docs/`.
- Windows machine: use forward slashes in commands; validator output may show mangled accents in the console.

## Docs

- `docs/format.md` - element-by-element XML reference with an example. Read before writing or fixing XML.
- `docs/classifications.md` - allowed `<classification subject>` values (generated from the XSD).
