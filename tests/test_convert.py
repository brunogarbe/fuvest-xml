"""Converter smoke tests: every verified exam must convert to LaTeX and HTML."""
from pathlib import Path

import pytest

from fuvest_xml.convert import HtmlWriter, LatexWriter, XmlConverter

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "xsd" / "fuvest_xml.xsd"
VERIFIED = sorted((ROOT / "exams" / "xml-verified").glob("*.xml"))
FIXTURE = ROOT / "tests" / "fixtures" / "option_verse.xml"


def convert(path, writer):
    converter = XmlConverter(writer)
    converter.global_graphics_dir = ROOT / "images"
    converter.read_xml(path)
    converter.validate_xml(SCHEMA)
    return converter.create_document()


@pytest.mark.parametrize("writer", [LatexWriter, HtmlWriter], ids=["latex", "html"])
@pytest.mark.parametrize("path", VERIFIED, ids=lambda p: p.name)
def test_verified_exam_converts(path, writer):
    assert convert(path, writer())


def test_option_verse_and_cite_are_rendered():
    latex = convert(FIXTURE, LatexWriter())
    html = convert(FIXTURE, HtmlWriter())
    assert "Vou passar, quero ver" in latex and "Duas Tribos" in latex
    assert "Vou passar, quero ver" in html and "Duas Tribos" in html


def test_wrapped_image_latex():
    out = LatexWriter().image("images/a.png", True, "0.4")
    assert "wrapfigure" in out and "includegraphics[width=\\linewidth]{images/a.png}" in out
