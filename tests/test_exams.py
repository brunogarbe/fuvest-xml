"""Corpus checks: every reviewed exam must validate against the XSD."""
from pathlib import Path

import pytest

from fuvest_xml.validate import validate_xml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "xsd" / "fuvest_xml.xsd"
VERIFIED = sorted((ROOT / "exams" / "xml-verified").glob("*.xml"))

# Known schema failures that still need fixing; remove entries once fixed.
KNOWN_FAILING = {"fuvest_2027_fase_01.xml"}


@pytest.mark.parametrize("path", VERIFIED, ids=lambda p: p.name)
def test_verified_exam_validates(path):
    if path.name in KNOWN_FAILING:
        pytest.xfail("known schema error")
    errors = validate_xml(str(SCHEMA), str(path))
    assert not errors, "\n".join(
        f"line {e['line']} {e.get('question', '')}: {e['message']}" for e in errors[:5]
    )


# Exams whose image folders are not in the repository yet.
KNOWN_MISSING_IMAGES = {
    "enem_2025_regular_dia_01.xml",
    "fuvest_1999_fase_01_prova_01.xml",
    "fuvest_1999_fase_01_prova_02.xml",
    "ita_2026_fase_01.xml",
    "unesp_2026_fase_01.xml",
    "unicamp_2026_fase_01.xml",
}


@pytest.mark.parametrize("path", VERIFIED, ids=lambda p: p.name)
def test_verified_images_exist(path):
    if path.name in KNOWN_MISSING_IMAGES:
        pytest.xfail("image files not in repository")
    from lxml import etree

    missing = [
        img.get("src")
        for img in etree.parse(str(path)).iter("image")
        if not (ROOT / "images" / img.get("src")).exists()
    ]
    assert not missing, f"missing images: {missing[:5]}"
