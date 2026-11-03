import shutil
from pathlib import Path

from fuvest_xml.pretty_print import pretty_print_xml
from fuvest_xml.validate import validate_xml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "xsd" / "fuvest_xml.xsd"
SAMPLE = ROOT / "exams" / "xml-verified" / "fuvest_2026_fase_01.xml"


def test_format_is_idempotent_and_keeps_validity(tmp_path):
    f = tmp_path / "exam.xml"
    shutil.copy(SAMPLE, f)
    pretty_print_xml(str(f))
    once = f.read_bytes()
    pretty_print_xml(str(f))
    assert f.read_bytes() == once
    assert validate_xml(str(SCHEMA), str(f)) == []


def test_validator_reports_question_label(tmp_path):
    f = tmp_path / "bad.xml"
    text = SAMPLE.read_text(encoding="utf-8").replace("<classification ", "<oops ", 1)
    f.write_text(text, encoding="utf-8")
    errors = validate_xml(str(SCHEMA), str(f))
    assert errors and errors[0]["question"].startswith("objective_question")
