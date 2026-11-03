# fuvest-xml

Tools for validating, converting, formatting, and indexing entrance-exam XML.
The command-line interfaces are built with [Typer](https://typer.tiangolo.com/).

## Setup

Install Python and all project dependencies into the managed environment:

```console
uv sync
```

## Command-line tools

Run a tool with `uv run <command> --help`:

- `fuvest-xml` / `fuvest-xml-convert`: convert XML to LaTeX or HTML.
- `fuvest-xml-convert-legacy`: run the older converter.
- `fuvest-xml-validate`: validate one file or a collection against the XSD.
- `fuvest-xml-format`: pretty-print an XML file in place.
- `fuvest-xml-db`: build and query the exam SQLite database.
- `fuvest-xml-gui`: launch the PyQt desktop interface.
- `fuvest-xml-read-pdfs`: recursively extract XML from PDFs under `exams/pdf`, writing to `exams/xml` and skipping XML files that already exist.

For example:

```console
uv run fuvest-xml-validate --help
uv run fuvest-xml exams/fuvest_2026_fase_01.xml --html
```

## Project layout

```text
exams/pdf/            source PDFs (local only)
exams/xml/            raw extracted XML (unreviewed)
exams/xml-verified/   hand-checked XML
images/               figures referenced by <image src>, relative to this folder
xsd/fuvest_xml.xsd    schema (source of truth)
src/fuvest_xml/       CLI tools
tests/                pytest checks
docs/                 XML format reference and classification list
```

Files are named `<exam>_<year>_fase_NN[_dia_NN|_<subject>].xml`.

## Development

```console
uv run pytest
uv run ruff check src tests
uv run fuvest-xml-validate "exams/xml/*.xml" --summary
```

LaTeX output needs a TeX distribution (e.g. TeX Live or MiKTeX) with the packages used by `styles/general.sty`.
AI-assistant guidance lives in `CLAUDE.md` and `docs/`.
