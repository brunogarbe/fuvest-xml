from pathlib import Path

from fuvest_xml.validate import validate_xml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "xsd" / "fuvest_xml.xsd"
FIXTURE = ROOT / "tests" / "fixtures" / "option_verse.xml"


def test_option_accepts_verse_and_cite():
    assert validate_xml(str(SCHEMA), str(FIXTURE)) == []
