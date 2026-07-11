"""Extract questions from a directory of exam PDFs into XSD-valid XML.

Pipeline for every PDF in the input directory:

    pymupdf text extraction
      -> normalization / paragraph splitting
      -> format-aware question + option/part detection
      -> lxml tree build (following the sequence in xsd/fuvest_xml.xsd)
      -> XSD validation (ENFORCED: invalid files are flagged, run exits non-zero)
      -> write to exams/<stem>.xml

The reference XMLs in ``reference/`` are hand/LLM-curated gold. They are used
here only as a quality *yardstick* (a similarity report is printed when a
reference exists) -- they are never copied into the output. Everything written
to ``outputs/`` is genuinely parsed from the PDF text layer.

Note on fidelity: LaTeX math, colored spans and figures live in the PDF as
images, not text, so they cannot be recovered from ``get_text()`` and are absent
from the generated XML. Fully scanned exams (no text layer, e.g. ITA) yield only
a flagged placeholder unless an OCR engine is installed.
"""

import re
from pathlib import Path

import pymupdf
from lxml import etree
import typer

app = typer.Typer(help="Extract XSD-valid exam XML from a directory of PDFs.")

DEFAULT_INPUT_DIR = Path("./exams/pdf")
DEFAULT_OUTPUT_DIR = Path("./exams/xml")
DEFAULT_REFERENCE_DIR = Path("./reference")
DEFAULT_XSD_PATH = Path("./xsd/fuvest_xml.xsd")

# Some of these PDFs encode ordinary spaces as U+00AC ("not" sign).
SPACE_HACK = "\xac"

# "Texto para as questoes 01 e 02" / "Texto para a questao 5"
CTX_PAT = re.compile(
    r"Texto\s+para\s+(?:as\s+quest[õo]es|a\s+quest[ãa]o)\s+"
    r"(?:de\s+)?(\d+)(?:\s*(?:e|a|,)\s*(\d+))?",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Text normalization
# --------------------------------------------------------------------------- #
def _dehyphenate(text):
    """Join words broken across a line by a trailing hyphen."""
    return re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)


# C0 control characters that are illegal in XML 1.0 (tab/LF/CR are allowed).
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_inline(text):
    """Collapse a chunk of text to a single, XML-safe normalized line."""
    text = text.replace(SPACE_HACK, " ")
    text = _dehyphenate(text)
    text = _ILLEGAL_XML.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def split_paragraphs(raw):
    """Split raw text into cleaned paragraphs on blank lines."""
    raw = raw.replace(SPACE_HACK, " ")
    out = []
    for part in re.split(r"\n\s*\n", raw):
        cleaned = clean_inline(part)
        if cleaned:
            out.append(cleaned)
    return out


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def detect_metadata(stem):
    low = stem.lower()

    year_m = re.search(r"(?:19|20)\d{2}", stem)
    year = year_m.group(0) if year_m else "2026"

    day_m = re.search(r"dia[_\- ]?(\d)", low)
    day = day_m.group(1) if day_m else "1"

    discursive = "fase_02" in low or "fase02" in low or "fase_2" in low

    if "fuvest" in low:
        name = "FUVEST"
    elif "enem" in low:
        name = "ENEM"
    elif "unicamp" in low:
        name = "UNICAMP"
    elif "ita" in low:
        name = "ITA"
    else:
        name = (re.split(r"[_\d]", stem)[0] or "EXAM").upper()

    return {
        "name": name,
        "year": year,
        "phase": "discursive" if discursive else "objective",
        "day": day,
        "variation": "AZUL" if name == "ENEM" else "V1",
        "date": f"{year}-01-01",
        "lang": "pt-br",
    }, discursive


# --------------------------------------------------------------------------- #
# Question splitting
# --------------------------------------------------------------------------- #
def _slice_on_matches(text, matches):
    """Turn regex match objects for question markers into (header, questions).

    The question number is the first non-empty capture group of each match, so
    a marker regex may use alternation. Consecutive markers with the same number
    are merged (some booklets list the numbers in a header before the body).
    """
    header = text[: matches[0].start()]
    questions = []
    for i, m in enumerate(matches):
        num = next((g for g in m.groups() if g), "")
        if num.isdigit():
            num = num.zfill(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        if questions and questions[-1][0] == num:
            questions[-1] = (num, questions[-1][1] + body)
        else:
            questions.append((num, body))
    return header, questions


def _split_sequential(text):
    """Split on question numbers that lead a line (1, 2, 3, ...).

    Handles both a number alone on its line and a number immediately followed
    by the question text on the same line (older FUVEST: ``01 "Pela primeira``).
    A false positive such as ``1,02 bilhão`` is rejected because the digit is
    not followed by whitespace/end-of-line.
    """
    lines = text.split("\n")
    expected = 1
    marks = []  # (line_index, number, marker_length)
    for idx, line in enumerate(lines):
        s = line.strip()
        m = re.match(rf"0*{expected}(?=\s|$)", s)
        if m:
            marks.append((idx, expected, m.end()))
            expected += 1
            if expected > 120:
                break
    if len(marks) < 10:
        return text, []

    header = "\n".join(lines[: marks[0][0]])
    questions = []
    for j, (li, num, mlen) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        remainder = lines[li].strip()[mlen:]
        body = "\n".join([remainder] + lines[li + 1:end])
        questions.append((f"{num:02d}", body))
    return header, questions


# Ordered by specificity; the first whose marker fires (>= threshold) wins.
# (mode, compiled regex capturing the question number, minimum count to accept)
_MARKER_MODES = [
    ("brace", re.compile(r"\{(\d{1,3})\}"), 10),                 # FUVEST 2025-2026
    ("subject", re.compile(r"\b([BFGHMQ]\d{2})\b"), 10),        # 2nd phase by subject
    ("questao", re.compile(r"QUEST[ÃA]O\s+(\d{1,3})", re.I), 10),  # ENEM / UNICAMP
    # Letter-dot marker: FUVEST 1999 "V.01 –" (dashed, may be mid-line) or
    # FUVEST 2nd phase 2004-2009 "Q.01" (line-leading). 10 questions/booklet.
    ("letterdot",
     re.compile(r"[A-Z]\.(\d{2})\s*[–-]|^[ \t]*[A-Z]\.(\d{2})(?=\s|$)", re.M),
     6),
]


def split_questions(text):
    """Detect the marker style and split. Returns (header, questions, mode)."""
    for mode, regex, threshold in _MARKER_MODES:
        matches = list(regex.finditer(text))
        if len(matches) >= threshold:
            header, questions = _slice_on_matches(text, matches)
            return header, questions, mode
    header, questions = _split_sequential(text)
    if questions:
        return header, questions, "sequential"
    return text, [], "none"


# --------------------------------------------------------------------------- #
# Context detection
# --------------------------------------------------------------------------- #
def find_context(raw):
    """Split a chunk around a 'Texto para as questoes ...' marker.

    Returns (text_before_marker, context_paragraphs_or_None, target_numbers).
    """
    m = CTX_PAT.search(raw)
    if not m:
        return raw, None, []

    g1, g2 = m.groups()
    if g1 and g2:
        lo, hi = int(g1), int(g2)
        targets = [f"{n:02d}" for n in range(lo, hi + 1)]
    else:
        targets = [f"{int(g1):02d}"]

    before = raw[: m.start()]
    context = split_paragraphs(raw[m.end():])
    return before, context, targets


# --------------------------------------------------------------------------- #
# Option / part detection
# --------------------------------------------------------------------------- #
def _is_sequential(labels, alphabet):
    """True if labels are a proper prefix of alphabet (A,B,C,... or a,b,...)."""
    n = len(labels)
    return n >= 2 and list(labels) == list(alphabet[:n])


def extract_options(body):
    """Detect multiple-choice options.

    Returns (statement_text, [(label, text), ...]) or None when no clean,
    sequential option block is found.
    """
    strategies = [
        (r"\(([A-E])\)\s*", "ABCDE"),                 # (A) (B) ...   FUVEST
        (r"(?m)^[ \t]*([A-E])\t+\s*", "ABCDE"),       # A<tab> ...     ENEM
        (r"(?:^|\s)([a-e])\)\s+", "abcde"),           # a) b) ...      UNICAMP
    ]
    best = None
    for pattern, alphabet in strategies:
        seg = re.split(pattern, body)
        labels = seg[1::2]
        texts = seg[2::2]
        if _is_sequential(labels, alphabet):
            cand = (seg[0], list(zip([lbl.upper() for lbl in labels], texts)))
            if best is None or len(cand[1]) > len(best[1]):
                best = cand
    return best


def extract_parts(body):
    """Detect discursive sub-item parts a) b) c).

    Returns (statement_text, [part_text, ...]).
    """
    seg = re.split(r"(?:^|\s)([a-e])\)\s+", body)
    labels = seg[1::2]
    if _is_sequential(labels, "abcde"):
        return seg[0], seg[2::2]
    return body, []


# --------------------------------------------------------------------------- #
# XML building helpers
# --------------------------------------------------------------------------- #
def _add_paragraphs(parent, paragraphs, fallback=""):
    """Add <p> children; guarantee at least one so required elements are valid."""
    added = False
    for para in paragraphs:
        p = etree.SubElement(parent, "p")
        p.text = para
        added = True
    if not added:
        p = etree.SubElement(parent, "p")
        p.text = fallback
    return parent


def build_objective_question(group, number, statement_paras, options):
    q = etree.SubElement(group, "objective_question", number=number)
    etree.SubElement(q, "classification", subject="Unknown")
    statement = etree.SubElement(q, "statement")
    _add_paragraphs(statement, statement_paras)
    opts = etree.SubElement(q, "options")
    for label, text in options:
        opt = etree.SubElement(opts, "option", label=label, is_correct="false")
        p = etree.SubElement(opt, "p")
        p.text = clean_inline(text)
    return q


def build_discursive_question(group, number, statement_paras, parts):
    q = etree.SubElement(group, "discursive_question", number=number)
    etree.SubElement(q, "classification", subject="Unknown")
    statement = etree.SubElement(q, "statement")
    _add_paragraphs(statement, statement_paras)
    parts_el = etree.SubElement(q, "parts")
    if not parts:
        parts = [""]
    for part_text in parts:
        part = etree.SubElement(parts_el, "part")
        p = etree.SubElement(part, "p")
        p.text = clean_inline(part_text)
    return q


def build_essay_question(group, number, statement_paras):
    q = etree.SubElement(group, "essay_question", number=number)
    statement = etree.SubElement(q, "statement")
    _add_paragraphs(statement, statement_paras, fallback="[Proposta de redação]")
    return q


# --------------------------------------------------------------------------- #
# PDF -> XML
# --------------------------------------------------------------------------- #
def extract_full_text(doc):
    return "".join(page.get_text() for page in doc)


def looks_garbled(text):
    """True when the text layer is mojibake (broken font/ToUnicode map).

    A working extraction is mostly letters; a broken CMap yields a stream of
    punctuation/symbol glyphs. Measured on the non-whitespace characters so
    that merely space-stripped (but readable) text is not misclassified.
    """
    sample = re.sub(r"\s", "", text)[:8000]
    if len(sample) < 200:
        return False
    alpha = sum(c.isalpha() for c in sample)
    return alpha / len(sample) < 0.55


def _placeholder_exam(exam, message):
    group = etree.SubElement(exam, "question_group")
    build_essay_question(group, "1", [message])


def parse_pdf(pdf_path):
    """Parse one PDF into an lxml <exam> element. Returns (element, note)."""
    meta, discursive = detect_metadata(pdf_path.stem)
    exam = etree.Element("exam", **meta)

    doc = pymupdf.open(pdf_path)
    full_text = extract_full_text(doc)
    note = None

    if len(full_text.strip()) < 200:
        # No usable text layer (scanned document). Emit a valid, flagged stub.
        note = "scanned PDF (no text layer) - only a placeholder was generated"
        _placeholder_exam(
            exam,
            "Documento digitalizado sem camada de texto; "
            "extração automática indisponível (OCR necessário).",
        )
        return exam, note

    if looks_garbled(full_text):
        # Text present but the font's ToUnicode map is broken -> unreadable.
        note = "garbled text layer (broken font encoding) - placeholder generated"
        _placeholder_exam(
            exam,
            "Camada de texto ilegível (codificação de fonte corrompida); "
            "extração automática indisponível (OCR necessário).",
        )
        return exam, note

    header, raw_questions, mode = split_questions(full_text)

    if not raw_questions:
        note = f"no question markers detected (mode={mode})"
        group = etree.SubElement(exam, "question_group")
        build_essay_question(group, "1", split_paragraphs(header) or [""])
        return exam, note

    # Map a shared context to the questions it introduces.
    context_map = {}

    def register(context, targets):
        if context and targets:
            for t in targets:
                context_map[t] = context

    _, ctx, targets = find_context(header)
    register(ctx, targets)

    # Separate each question's own body from any trailing context it introduces.
    questions = []
    for num, body in raw_questions:
        before, ctx, targets = find_context(body)
        register(ctx, targets)
        questions.append((num, before))

    # Group consecutive questions that share the same context object.
    groups = []
    current_ctx = ...  # sentinel distinct from any real value (incl. None)
    current = []
    for num, body in questions:
        ctx = context_map.get(num)
        if ctx == current_ctx and current:
            current.append((num, body))
        else:
            if current:
                groups.append((current_ctx, current))
            current_ctx = ctx
            current = [(num, body)]
    if current:
        groups.append((current_ctx, current))

    for ctx, members in groups:
        group = etree.SubElement(exam, "question_group")
        if ctx:
            context_el = etree.SubElement(group, "context")
            _add_paragraphs(context_el, ctx)

        for num, body in members:
            if discursive:
                statement, parts = extract_parts(body)
                statement_paras = split_paragraphs(statement)
                if parts:
                    build_discursive_question(group, num, statement_paras, parts)
                else:
                    build_essay_question(group, num, statement_paras or [""])
            else:
                found = extract_options(body)
                if found and len(found[1]) >= 3:
                    statement_paras = split_paragraphs(found[0])
                    build_objective_question(group, num, statement_paras, found[1])
                else:
                    # No clean options -> keep it valid as a discursive item.
                    statement, parts = extract_parts(body)
                    statement_paras = split_paragraphs(statement)
                    if parts:
                        build_discursive_question(group, num, statement_paras, parts)
                    else:
                        build_essay_question(group, num, statement_paras or [""])

    return exam, note


# --------------------------------------------------------------------------- #
# Validation & scoring
# --------------------------------------------------------------------------- #
def load_schema(xsd_path):
    return etree.XMLSchema(etree.parse(str(xsd_path)))


def count_questions(xml_bytes):
    root = etree.fromstring(xml_bytes)
    tags = ("objective_question", "discursive_question", "essay_question")
    n_q = sum(len(root.findall(f".//{t}")) for t in tags)
    n_opt = len(root.findall(".//option"))
    return n_q, n_opt


def score_against_reference(stem, xml_bytes, reference_dir):
    ref = reference_dir / f"{stem}.xml"
    if not ref.exists():
        return None
    try:
        rq, ro = count_questions(ref.read_bytes())
        gq, go = count_questions(xml_bytes)
    except etree.XMLSyntaxError:
        return None
    return f"questions {gq}/{rq}, options {go}/{ro} (generated/reference)"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
@app.command()
def read_pdfs_command(
    input_dir: Path = typer.Argument(
        DEFAULT_INPUT_DIR,
        help="Directory containing the PDF files to process.",
    ),
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Directory where generated XML files are written.",
    ),
    schema: Path = typer.Option(
        DEFAULT_XSD_PATH,
        "--schema",
        help="Path to the Fuvest XML Schema.",
    ),
    reference_dir: Path = typer.Option(
        DEFAULT_REFERENCE_DIR,
        "--reference-dir",
        help="Optional directory containing reference XML files for scoring.",
    ),
) -> None:
    if not input_dir.is_dir():
        typer.echo(f"Input directory not found: {input_dir}", err=True)
        raise typer.Exit(code=1)
    if not schema.is_file():
        typer.echo(f"Schema file not found: {schema}", err=True)
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    xml_schema = load_schema(schema)

    pdf_files = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdf_files:
        typer.echo(f"No PDF files found in {input_dir}.")
        return

    invalid = []
    processed = 0
    skipped = 0
    for pdf_file in pdf_files:
        out_file = output_dir / f"{pdf_file.stem}.xml"
        if out_file.exists():
            typer.echo(f"Skipping {pdf_file.name}: {out_file} already exists.")
            skipped += 1
            continue

        typer.echo(f"\nProcessing {pdf_file.name} ...")
        try:
            exam, note = parse_pdf(pdf_file)
        except Exception as exc:  # keep processing the rest
            typer.echo(f"  ERROR while parsing: {exc}", err=True)
            invalid.append(pdf_file.stem)
            continue

        xml_bytes = etree.tostring(
            exam, xml_declaration=True, encoding="utf-8", pretty_print=True
        )

        valid = xml_schema.validate(exam)
        if valid:
            typer.echo("  XSD: valid")
        else:
            invalid.append(pdf_file.stem)
            first = xml_schema.error_log[0] if len(xml_schema.error_log) else None
            typer.echo(
                f"  XSD: INVALID -> {first.message if first else 'unknown error'}",
                err=True,
            )

        if note:
            typer.echo(f"  note: {note}")

        score = score_against_reference(pdf_file.stem, xml_bytes, reference_dir)
        if score:
            typer.echo(f"  vs reference: {score}")

        try:
            with out_file.open("xb") as output_stream:
                output_stream.write(xml_bytes)
        except FileExistsError:
            typer.echo(f"  skipped write: {out_file} already exists.")
            skipped += 1
            continue
        processed += 1
        typer.echo(f"  wrote {out_file}")

    typer.echo("\n" + "=" * 60)
    if invalid:
        typer.echo(
            f"FAILED XSD validation for {len(invalid)} file(s): "
            f"{', '.join(invalid)}",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(
        f"Completed: {processed} processed, {skipped} skipped, "
        f"{len(pdf_files)} PDF file(s) found."
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
