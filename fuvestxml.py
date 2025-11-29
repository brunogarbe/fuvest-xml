#!/usr/bin/env python3
"""
xml_exam_to_latex.py

Validate an exam XML against an XSD, and render it to a LaTeX file.

Usage:
  python xml_exam_to_latex.py input.xml schema.xsd output.tex [--graphics-dir DIR] [--docclass CLASS]

Notes:
- Expects an XML of the form:
  <exam name="..." year="..." phase="..." ...>
    <question_group> ... </question_group>
    ...
  </exam>
- Supported child elements inside <statement>: <p>, <quote> (with <p>, <author>), <image src="..."/>, <table>, <ul><li>, and <context> blocks.
- Supported options: <options><option label="A"><p>...</p></option>...</options>
- If <correct_answer> has text, it will be collected for an Answer Key at the end.
"""

import os
import argparse
import re
import sys
from abc import ABC, abstractmethod
from typing import override
from pathlib import Path

from lxml import etree
import random

FOOTNOTES_SYMBOLS = [
    "*",
    "**",
    "***",
    "****",
    "*****",
]

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# -----------------------------------------------------------------
#  Auxiliary functions
# -----------------------------------------------------------------

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# number_to_letter auxiliar function


def number_to_letter(number) -> str:
    """
    Converts an integer (1-26) to its corresponding uppercase letter (A-Z).

    Args:
    number: An integer between 1 and 26 (inclusive).

    Returns:
    The corresponding uppercase letter, or a ValueError if the input is out of range.
    """
    if not 1 <= number <= 26:
        raise ValueError("Input number must be between 1 and 26.")

    return str(chr(64 + number))


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# search_database


def shuffle_questions(q):
    # Step 1: Extract option children and their positions
    option_positions = []
    option_nodes = []

    options = q.find("./options")

    if options is None:
        options = q.find("./options_table")

    # print(options)

    for i, child in enumerate(options):
        if child.tag == "option":
            option_positions.append(i)
            option_nodes.append(child)

    # Step 2: Shuffle the option nodes
    random.shuffle(option_nodes)

    # Step 3: Reinsert shuffled options at their original positions
    for pos, node in zip(option_positions, option_nodes):
        # print(pos, fuvestxml.number_to_letter(pos + 1))
        # print(ET.tostring(node, encoding="unicode"))
        node.set("label", number_to_letter(pos + 1))
        options[pos] = node


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <image> tag


def xml_to_python_boolean(xml_string):
    if xml_string.lower() == "true":
        return True
    elif xml_string.lower() == "false":
        return False
    else:
        # Handle cases where the string is not "true" or "false"
        # You might raise an error, return None, or a default boolean
        raise ValueError(f"Invalid boolean string: {xml_string}")


# -----------------------------------------------------------------
# 1. The Strategy Interface
# -----------------------------------------------------------------
# Defines the common interface for all output algorithms.
# The Context will call this method.
#
class AbstractWriter(ABC):
    """
    The Strategy interface declares operations common to all supported
    versions of some algorithm. The Context uses this interface to
    call the algorithm defined by Concrete Strategies.
    """

    # Body of document
    @abstractmethod
    def preamble(self, title: str) -> str:
        pass

    @abstractmethod
    def body_start(self) -> str:
        pass

    @abstractmethod
    def body_end(self) -> str:
        pass

    # Sections processing
    # Context
    @abstractmethod
    def context_start(self, text: str) -> str:
        pass

    @abstractmethod
    def context_end(self) -> str:
        pass

    # Question
    @abstractmethod
    def question_start(self, number: str) -> str:
        pass

    @abstractmethod
    def question_end(self) -> str:
        pass

    # Regular options
    @abstractmethod
    def options_regular_start(self) -> str:
        pass

    @abstractmethod
    def options_regular_end(self) -> str:
        pass

    @abstractmethod
    def options_item_start(self) -> str:
        pass

    @abstractmethod
    def options_item_end(self) -> str:
        pass

    # Table options
    @abstractmethod
    def options_table_start(self, num_cols: int, table_class: str) -> str:
        pass

    @abstractmethod
    def options_table_end(self) -> str:
        pass

    @abstractmethod
    def options_header_start(self) -> str:
        pass

    @abstractmethod
    def options_header_end(self) -> str:
        pass

    @abstractmethod
    def options_row_start(self, option_text: str) -> str:
        pass

    @abstractmethod
    def options_row_end(self) -> str:
        pass

    @abstractmethod
    def options_cell_start(self, align: str) -> str:
        pass

    @abstractmethod
    def options_cell_end(self) -> str:
        pass

    # Assumptions
    @abstractmethod
    def assumptions_start(self) -> str:
        pass

    @abstractmethod
    def assumptions_end(self) -> str:
        pass

    @abstractmethod
    def paragraph(self, text: str) -> str:
        pass

    @abstractmethod
    def header(self, text: str) -> str:
        pass

    @abstractmethod
    def caption(self, text: str) -> str:
        pass

    # Display Quote
    @abstractmethod
    def display_quote_start(self) -> str:
        pass

    @abstractmethod
    def display_quote_end(self) -> str:
        pass

    # Verse
    @abstractmethod
    def verse_start(self) -> str:
        pass

    @abstractmethod
    def verse_end(self) -> str:
        pass

    @abstractmethod
    def verse_title(self, text: str) -> str:
        pass

    @abstractmethod
    def verse_stanza_start(self) -> str:
        pass

    @abstractmethod
    def verse_stanza_end(self) -> str:
        pass

    @abstractmethod
    def verse_line(self, text: str) -> str:
        pass

    # Image
    @abstractmethod
    def image(self, img_path: str, wrap: bool, width: str, html_width: str) -> str:
        pass

    @abstractmethod
    def inline_image(
        self, img_path: str, wrap: bool, width: str, html_width: str
    ) -> str:
        pass

    # Table
    @abstractmethod
    def table_start(self, column_spec: list[str], width: int) -> str:
        pass

    @abstractmethod
    def table_end(self) -> str:
        pass

    @abstractmethod
    def table_row_start(self) -> str:
        pass

    @abstractmethod
    def table_row_end(self) -> str:
        pass

    @abstractmethod
    def table_cell_start(self) -> str:
        pass

    @abstractmethod
    def table_cell_end(self) -> str:
        pass

    # List
    @abstractmethod
    def list_start(self) -> str:
        pass

    @abstractmethod
    def list_end(self) -> str:
        pass

    @abstractmethod
    def list_item_start(self) -> str:
        pass

    @abstractmethod
    def list_item_end(self) -> str:
        pass

    @abstractmethod
    def ordered_list_start(self) -> str:
        pass

    @abstractmethod
    def ordered_list_end(self) -> str:
        pass

    @abstractmethod
    def ordered_list_item_start(self) -> str:
        pass

    @abstractmethod
    def ordered_list_item_end(self) -> str:
        pass

    @abstractmethod
    def cite(self, text: str) -> str:
        pass

    # Inlines
    @abstractmethod
    def bold(self, text: str) -> str:
        pass

    @abstractmethod
    def italic(self, text: str) -> str:
        pass

    @abstractmethod
    def underline(self, text: str) -> str:
        pass

    @abstractmethod
    def quote(self, text: str) -> str:
        pass

    @abstractmethod
    def style(self, text: str, color: str) -> str:
        pass

    @abstractmethod
    def math(self, text: str) -> str:
        pass

    @abstractmethod
    def display_math(self, text: str, end_symbol: str) -> str:
        pass

    @abstractmethod
    def chemistry(self, text: str) -> str:
        pass

    @abstractmethod
    def display_chemistry(self, text: str, end_symbol: str) -> str:
        pass

    @abstractmethod
    def reference(self, text: str) -> str:
        pass

    @abstractmethod
    def clean_text(self, text: str) -> str:
        pass

    @abstractmethod
    def clean_math(self, text: str) -> str:
        pass

    @abstractmethod
    def clean_chemistry(self, text: str) -> str:
        pass


# -----------------------------------------------------------------
# 2. The Concrete Strategies
# -----------------------------------------------------------------
# Implement the algorithm (output generation) in different ways.


class LatexWriter(AbstractWriter):
    """
    Implements the algorithm using the LaTeX format.
    """

    def __init__(self):
        self.table_width = 0
        # for control of the output in a table
        self.table_counter = 0
        self.table_num_columns = 0

    @override
    def preamble(self, title: str) -> str:
        parts = [
            "\\documentclass[11pt,a4paper,twocolumn]{article}\n\\usepackage{styles/general}\n\n"
        ]
        # \usepackage{url} % Required for clickable links
        # \title{My Document Title}
        # \author{Alice Wonderland, \url{alice.w@example.com}}
        parts.append("\\title{\\textbf{" + title + "}}\n")
        parts.append("\\author{FuvestXML}\n")
        parts.append("\\date{2022-01-01}\n")
        parts.append("\n")

        return "".join(parts)

    @override
    def body_start(self) -> str:
        return "\\begin{document}\n\n\\maketitle\n\n"

    @override
    def body_end(self) -> str:
        return "\\end{document}\n"

    @override
    def context_start(self, text: str) -> str:
        parts = []
        parts.append("\\vspace{18pt}\n\n")
        parts.append("\\begin{center}\n")
        parts.append(f"\\textbf{{{text}}}\n")
        parts.append("\\end{center}\n\n")

        return "".join(parts)

    @override
    def context_end(self) -> str:
        return "\\centerline{\\rule{5cm}{0.5pt}}\n\n"

    @override
    def question_start(self, number: str) -> str:
        parts = []
        parts.append(
            "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n"
        )
        parts.append(f"% Question {number}\n\n")
        parts.append("\\section{}\n\n")

        return "".join(parts)

    @override
    def question_end(self) -> str:
        return "\\centerline{\\rule{5cm}{0.5pt}}\n\n"

    @override
    def options_regular_start(self) -> str:
        return "\\begin{enumerate}\n"

    @override
    def options_regular_end(self) -> str:
        return "\\end{enumerate}\n\n"

    @override
    def options_item_start(self) -> str:
        return "\\item "

    @override
    def options_item_end(self) -> str:
        return "\n"

    @override
    def options_table_start(self, num_cols: int) -> str:
        parts = []

        self.table_num_columns = num_cols

        colspec = "|".join(["X"] * num_cols)
        parts.append("\\begin{center}\n")
        parts.append("\\begin{tabularx}{\\linewidth}{|c|" + colspec + "|}\n")
        parts.append("\\hline\n")

        return "".join(parts)

    @override
    def options_table_end(self) -> str:
        self.table_num_columns = -1
        parts = []

        parts.append("\\end{tabularx}\n")
        parts.append("\\end{center}\n\n")

        return "".join(parts)

    @override
    def options_header_start(self) -> str:
        self.table_counter = 0
        return ""

    @override
    def options_header_end(self) -> str:
        parts = []
        parts.append("\\\\\n")
        parts.append("\\hline\n")
        return "".join(parts)

    @override
    def options_row_start(self, option_text: str) -> str:
        self.table_counter = 0
        option_text = option_text if option_text == "" else f" ({option_text}) "
        return option_text

    @override
    def options_row_end(self) -> str:
        parts = []
        parts.append("\\\\\n")
        parts.append("\\hline\n")
        return "".join(parts)

    @override
    def options_cell_start(self, align: str) -> str:
        return ""

    @override
    def options_cell_end(self) -> str:
        # print(self.table_counter, self.table_num_columns)
        if self.table_counter == (self.table_num_columns - 1):
            return ""
        else:
            # print("*")
            self.table_counter = self.table_counter + 1
            return " & "

    @override
    def assumptions_start(self) -> str:
        parts = []
        parts.append("\\begin{assumptionBox}\n")
        parts.append("\\textit{Note e adote:}\n\n")

        return "".join(parts)

    @override
    def assumptions_end(self) -> str:
        parts = []
        parts.append("\\end{assumptionBox}\n")

        return "".join(parts)

    @override
    def paragraph(self, text: str) -> str:
        end_par = "\n\n"
        return text + end_par

    @override
    def header(self, text: str) -> str:
        return f"\\textbf{{{text}}}\n\n"

    @override
    def display_quote_start(self) -> str:
        return "\\begin{displayquote}\n"

    @override
    def display_quote_end(self) -> str:
        parts = []
        parts.append("\\end{displayquote}\n")
        parts.append("\n")
        return "".join(parts)

    @override
    def verse_start(self) -> str:
        return "\\begin{verseblock}\n"

    @override
    def verse_end(self) -> str:
        return "\\end{verseblock}\n\n"

    @override
    def verse_title(self, text: str) -> str:
        return "\\textbf{" + text + "}\\\\\n"

    @override
    def verse_stanza_start(self) -> str:
        return ""

    @override
    def verse_stanza_end(self) -> str:
        return ""

    @override
    def verse_line(self, text: str) -> str:
        return text + "\\\\\n"

    @override
    def image(self, img_path: str, wrap: bool, width: str) -> str:
        parts = []
        if wrap is True:
            parts.append("\\begin{wrapfigure}{l}[0pt]{" + width + "\\linewidth}\n")
            parts.append("\\centering\n")
            parts.append(
                "\\includegraphics[width="
                + size
                + "]{"
                + str(img_path).replace("\\", "/")
                + "}\n"
            )
            parts.append("\\end{wrapfigure}\n\n")
        else:
            parts.append("\\begin{center}\n")
            parts.append(
                "\\includegraphics[width="
                + width
                + "\\linewidth]{"
                + str(img_path).replace("\\", "/")
                + "}\n"
            )
            parts.append("\\end{center}\n\n")
        return "".join(parts)

    @override
    def inline_image(self, img_path: str, wrap: bool, width: str) -> str:
        return (
            "\\includegraphics[width="
            + width
            + "\\linewidth]{"
            + str(img_path).replace("\\", "/")
            + "}"
        )

    # Table
    @override
    def table_start(self, column_spec: list[str], width: str) -> str:
        colspec = "|".join(column_spec)
        self.table_width = width
        self.table_num_columns = len(column_spec)

        parts = []
        parts.append("\\begin{center}\n")
        if width == 0:
            parts.append("\\begin{tabular}{|" + colspec + "|}\n")
        else:
            width_str = f"{width / 100.0:.2f}"
            parts.append(
                "\\begin{tabularx}{" + width_str + "\\linewidth}{|" + colspec + "|}\n"
            )
        parts.append("\\hline\n")
        return "".join(parts)

    @override
    def table_end(self) -> str:
        self.table_num_columns = -1
        parts = []
        if self.table_width == 0:
            parts.append("\\end{tabular}\n")
        else:
            parts.append("\\end{tabularx}\n")
        parts.append("\\end{center}\n\n")

        self.table_width = 0

        return "".join(parts)

    @override
    def table_row_start(self) -> str:
        self.table_counter = 0
        return ""

    @override
    def table_row_end(self) -> str:
        parts = []
        parts.append(" \\\\\n")
        parts.append("\\hline\n")
        return "".join(parts)

    @override
    def table_cell_start(self) -> str:
        return ""

    @override
    def table_cell_end(self) -> str:
        # print(self.table_counter, self.table_num_columns)
        if self.table_counter == (self.table_num_columns - 1):
            return ""
        else:
            # print("*")
            self.table_counter = self.table_counter + 1
            return " & "

    # List
    @override
    def list_start(self, symbol) -> str:
        return "\\begin{itemize}\n"

    @override
    def list_end(self) -> str:
        return "\\end{itemize}\n\n"

    @override
    def list_item_start(self) -> str:
        return "\\item "

    @override
    def list_item_end(self) -> str:
        return ""

    # List
    @override
    def ordered_list_start(self) -> str:
        return "\\begin{enumerate}\n"

    @override
    def ordered_list_end(self) -> str:
        return "\\end{enumerate}\n\n"

    @override
    def ordered_list_item_start(self) -> str:
        return "\\item "

    @override
    def ordered_list_item_end(self) -> str:
        return ""

    @override
    def cite(self, text: str) -> str:
        return f"\\quoteauthor{{{text}}}\n\n"

    # Inlines
    @override
    def bold(self, text: str) -> str:
        return f"\\textbf{{{text}}}"

    @override
    def italic(self, text: str) -> str:
        return f"\\textit{{{text}}}"

    @override
    def underline(self, text: str) -> str:
        return f"\\underline{{{text}}}"

    @override
    def quote(self, text: str) -> str:
        return f"“{text}”"

    @override
    def math(self, text: str) -> str:
        return f"${text}$"

    @override
    def display_math(self, text: str, end_symbol: str) -> str:
        return f"\n$${text} {end_symbol}$$\n"

    @override
    def chemistry(self, text: str) -> str:
        return f"\\ce{{{text}}}"

    @override
    def display_chemistry(self, text: str, end_symbol: str) -> str:
        return f"$$\\ce{{{text}}}$$"

    @override
    def reference(self, text: str) -> str:
        return f"$^{{\\mathrm{{{text}}} }}$"

    @override
    def clean_text(self, text: str) -> str:
        # Dictionary of characters to escape
        escape_map = {
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "→": r"->",
            "⇌": r"<=>",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
            "\\": r"\textbackslash{}",
        }

        # Create a regex from the keys of the map
        escape_regex = re.compile("|".join(map(re.escape, escape_map.keys())))

        # Perform the replacement
        fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

        return fully_escaped_text

    @override
    def clean_math(self, text: str) -> str:
        # Dictionary of characters to escape
        escape_map = {
            "π": r"\pi",
        }

        # Create a regex from the keys of the map
        escape_regex = re.compile("|".join(map(re.escape, escape_map.keys())))

        # Perform the replacement
        fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

        return fully_escaped_text

    @override
    def clean_chemistry(self, text: str) -> str:
        # Dictionary of characters to escape
        escape_map = {
            "α": r"\alpha",
            "→": r"->",
            "⇌": r"<=>",
        }

        # Create a regex from the keys of the map
        escape_regex = re.compile("|".join(map(re.escape, escape_map.keys())))

        # Perform the replacement
        fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

        return fully_escaped_text


class HtmlWriter(AbstractWriter):
    """
    Implements the algorithm using the LaTeX format.
    """

    def __init__(self):
        self.table_width = 0
        # for control of the output in a table
        self.table_counter = 0
        self.table_num_columns = 0
        self.title = ""

    @override
    def preamble(self, title: str) -> str:
        parts = [
            '<!DOCTYPE html>\n<html lang="en">\n',
            "<head>",
            '<link href="../css/basic.css" rel="stylesheet" />\n',
            '<script type="text/javascript" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>n',
            "</head>",
        ]

        self.title = title

        return "".join(parts)

    @override
    def body_start(self) -> str:
        return f'<body>\n<div class="container">\n<h1>{self.title}</h1>\n\n'

    @override
    def body_end(self) -> str:
        return "</div>\n</body>\n</html>\n"

    @override
    def context_start(self, text: str) -> str:
        parts = ['<div class="context-section">\n', f"<h4>{text}</h4>\n"]
        return "".join(parts)

    @override
    def context_end(self) -> str:
        return "</div>\n"

    @override
    def question_start(self, number: str) -> str:
        return '<section class="question-class">\n\t<h2>' + number + "</h2>\n"

    @override
    def question_end(self) -> str:
        return "</section>\n\n"

    @override
    def options_regular_start(self) -> str:
        return '\t<ol class="options" type="A">\n'

    @override
    def options_regular_end(self) -> str:
        return "\t</ol>\n"

    @override
    def options_item_start(self) -> str:
        return "\t\t<li>"

    @override
    def options_item_end(self) -> str:
        return "</li>\n"

    @override
    def options_table_start(self, num_cols: int, table_class: str) -> str:
        if table_class is None:
            return '\t<div class="table-option"><table>\n'
        else:
            return f'\t<div class="table-option-{table_class}"><table>\n'

    @override
    def options_table_end(self) -> str:
        return "\t</table>\n"

    @override
    def options_header_start(self) -> str:
        parts = ["<tr>\n", "<td></td>\n"]
        return "".join(parts)

    @override
    def options_header_end(self) -> str:
        return "</tr>\n"

    @override
    def options_row_start(self, option_text: str) -> str:
        option_text = option_text if option_text == "" else f" ({option_text}) "
        parts = ["<tr>\n", f"<td>{option_text}</td>\n"]
        return "".join(parts)

    @override
    def options_row_end(self) -> str:
        return "</tr>\n"

    @override
    def options_cell_start(self, align: str) -> str:
        if align == "center":
            return '<td class="cell-center">\n'
        else:
            return "<td>\n"

    @override
    def options_cell_end(self) -> str:
        return "</td>\n"

    @override
    def assumptions_start(self) -> str:
        parts = ['<div class="assumption-box">\n', "<h3>Note e adote:</h3>\n"]
        return "".join(parts)

    @override
    def assumptions_end(self) -> str:
        return "</div>\n"

    @override
    def paragraph(self, text: str) -> str:
        return "\t<p>" + text + "</p>\n"

    @override
    def header(self, text: str) -> str:
        return "\t<h3>" + text + "</h3>\n"

    @override
    def caption(self, text: str) -> str:
        return "<h6>" + text + "</h6>\n"

    @override
    def display_quote_start(self) -> str:
        return "\t<blockquote>\n"

    @override
    def display_quote_end(self) -> str:
        return "\t</blockquote>\n"

    @override
    def verse_start(self) -> str:
        return '<section class="verse_section">\n'

    @override
    def verse_end(self) -> str:
        return "</section>\n"

    @override
    def verse_title(self, text: str) -> str:
        return "<h3>" + text + "</h3>\n"

    @override
    def verse_stanza_start(self) -> str:
        return "<p>"

    @override
    def verse_stanza_end(self) -> str:
        return "</p>\n"

    @override
    def verse_line(self, text: str) -> str:
        return text + "<br/>\n"

    @override
    def image(self, img_path: str, wrap: bool, width: str, html_width: str) -> str:
        parts = []
        parts.append('\t<div class="image_container">\n')
        parts.append(
            "\t\t<img src="
            + str(img_path).replace("\\", "/")
            + ' width="'
            + html_width
            + '">\n'
        )
        parts.append("\t</div>\n")

        return "".join(parts)

    @override
    def inline_image(
        self, img_path: str, wrap: bool, width: str, html_width: str
    ) -> str:
        return (
            "<img src="
            + str(img_path).replace("\\", "/")
            + ' width="'
            + html_width
            + '">\n'
        )

    # Table
    @override
    def table_start(self, column_spec: list[str], width: str) -> str:
        colspec = "|".join(column_spec)
        self.table_width = width
        self.table_num_columns = len(column_spec)
        return '<div class="table-section"><table>\n'

    @override
    def table_end(self) -> str:
        return "</table></div>\n"

    @override
    def table_row_start(self) -> str:
        self.table_counter = 0
        return "<tr>\n"

    @override
    def table_row_end(self) -> str:
        return "</tr>\n"

    @override
    def table_cell_start(self) -> str:
        return "<td>\n"

    @override
    def table_cell_end(self) -> str:
        return "</td>\n"

    # List
    @override
    def list_start(self, symbol) -> str:
        if symbol is None:
            return "<ul>\n"
        else:
            return '<ul style="list-style-type: none;">' + symbol

    @override
    def list_end(self) -> str:
        return "</ul>\n\n"

    @override
    def list_item_start(self) -> str:
        return "<li>"

    @override
    def list_item_end(self) -> str:
        return "</li>\n"

    # List
    @override
    def ordered_list_start(self) -> str:
        return "<ul>\n"

    @override
    def ordered_list_end(self) -> str:
        return "</ul>\n\n"

    @override
    def ordered_list_item_start(self) -> str:
        return "<li>"

    @override
    def ordered_list_item_end(self) -> str:
        return "</li>"

    @override
    def cite(self, text: str) -> str:
        return f'\t<p class="cite_par"><cite>—{text}</cite></p>\n'

    # Inlines
    @override
    def bold(self, text: str) -> str:
        return "<b>" + text + "</b>\n"

    @override
    def italic(self, text: str) -> str:
        return "<i>" + text + "</i>\n"

    @override
    def underline(self, text: str) -> str:
        return "<u>" + text + "</u>\n"

    @override
    def quote(self, text: str) -> str:
        return f"<q>{text}</q>"

    @override
    def style(self, text: str, color: str) -> str:
        return f'<span style="color: {color};">{text}</span>'

    @override
    def math(self, text: str) -> str:
        return f"\\({text}\\)"

    @override
    def display_math(self, text: str, end_symbol: str) -> str:
        if end_symbol == "":
            return f"\n\\[{text}\\]\n"
        else:
            return f"\n\\[{text}{end_symbol}\\]\n"

    @override
    def chemistry(self, text: str) -> str:
        return f"\\(\\ce{{{text}}}\\)"

    @override
    def display_chemistry(self, text: str, end_symbol: str) -> str:
        if end_symbol == "":
            return f"\\[\\ce{{{text}}}\\]"
        else:
            return f"\\[\\ce{{{text}{end_symbol}}}\\]"

    @override
    def reference(self, text: str) -> str:
        return f"$^{{\\mathrm{{{text}}} }}$"

    @override
    def clean_text(self, text: str) -> str:
        # Dictionary of characters to escape
        escape_map = {
            "~": "\u202f",
        }

        # Create a regex from the keys of the map
        escape_regex = re.compile("|".join(map(re.escape, escape_map.keys())))

        # Perform the replacement
        fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

        return fully_escaped_text

    @override
    def clean_math(self, text: str) -> str:
        # Dictionary of characters to escape
        escape_map = {
            "π": r"\pi",
        }

        # Create a regex from the keys of the map
        escape_regex = re.compile("|".join(map(re.escape, escape_map.keys())))

        # Perform the replacement
        fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

        return fully_escaped_text

    @override
    def clean_chemistry(self, text: str) -> str:
        # Dictionary of characters to escape
        escape_map = {
            "α": r"\alpha",
            "→": r"->",
            "⇌": r"<=>",
        }

        # Create a regex from the keys of the map
        escape_regex = re.compile("|".join(map(re.escape, escape_map.keys())))

        # Perform the replacement
        fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

        return fully_escaped_text


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag

# class OutputStrategy(ABC):
#     """
#     The Strategy interface declares operations common to all supported
#     versions of some algorithm. The Context uses this interface to
#     call the algorithm defined by Concrete Strategies.
#     """
#     @abstractmethod
#     def generate_output(self, content: str) -> str:
#         pass


class XmlConverter:
    def __init__(self, writer: AbstractWriter) -> None:
        self.writer = writer
        self.global_graphics_dir = None
        self.global_footnote_struct = {}
        self.input = None

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Read a xml file to the input

    def read_xml(self, xml_path: Path) -> etree._ElementTree:
        parser = etree.XMLParser(remove_blank_text=True)
        self.input = etree.parse(str(xml_path), parser).getroot()

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Read a xml file to the input

    def read_xml_from_memory(self, input: etree._ElementTree):
        self.input = input

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Validate the xml input to a xml schema

    def validate_xml(self, xsd_path: Path) -> None:
        xmlschema_doc = etree.parse(str(xsd_path))
        xmlschema = etree.XMLSchema(xmlschema_doc)
        if not xmlschema.validate(self.input):
            log = xmlschema.error_log
            # Build a readable error message
            messages = ["XML does not conform to the provided XSD schema:"]
            for e in log:
                messages.append(f"  Line {e.line}, Col {e.column}: {e.message}")
            raise ValueError("\n".join(messages))

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # create_document()

    def create_document(self) -> str:
        root = self.input
        name = root.get("name", "Exam")
        year = root.get("year", "")
        phase = root.get("phase", "")
        day = root.get("day", "")
        variation = root.get("variation", "")

        # Variable to store the body commands create by the render functions
        body = []

        # Header
        title = f"{self.writer.clean_text(name) + ' ' + self.writer.clean_text(year)}"

        body.append(self.writer.preamble(title))
        body.append(self.writer.body_start())

        # Iterate over the exam child tags
        for child in root:
            if child.tag == "subject":
                for sub_child in child:
                    body.append(self.render_question_group(sub_child))

            elif child.tag == "question_group":
                body.append(self.render_question_group(child))

            else:
                raise ValueError("Tag not recognized!")

        # Ending
        body.append(self.writer.body_end())

        return "".join(body)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # create_document()
    # Inner function to process question_groups tags
    def render_question_group(self, parent):
        body = []

        # reset the footnote structure
        self.reset_footnotes()

        obj_questions = parent.findall("./objective_question")
        min_question = 1000
        max_question = 0
        if len(obj_questions) > 1:
            for q in obj_questions:
                number = int(q.get("number", "").strip())
                min_question = min_question if number > min_question else number
                max_question = max_question if number < max_question else number

        for child in parent:
            if child.tag == "context":
                body.append(
                    self.render_context(
                        child, len(obj_questions), min_question, max_question
                    )
                )
            elif child.tag == "objective_question":
                body.append(self.render_objective_question(child))

            elif child.tag == "discursive_question":
                raise NotImplementedError("discursive_question not implemented!")

            else:
                raise ValueError("Tag not recognized!")

        return "".join(body)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <context> tag

    def render_context(
        self, ctx_el, num_questions=1, min_question=0, max_question=0
    ) -> str:
        # Variable to store the body commands create by the render functions
        parts = []

        # get the right text according to the number of questions
        if num_questions == 1:
            text = f"TEXTO PARA A QUESTÃO {min_question}"

        elif num_questions == 2:
            text = f"TEXTO PARA AS QUESTÕES {min_question} E {max_question}"

        elif num_questions > 2:
            text = f"TEXTO PARA AS QUESTÕES DE {min_question} A {max_question}"

        # Context header
        parts.append(self.writer.context_start(text))

        # context may contain paragraphs and other elements
        for child in ctx_el:
            parts.append(self.render_blocks(child))

        # context close
        parts.append(self.writer.context_end())

        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <objective_question> tag

    def render_objective_question(self, q_el):
        # get the <objective_question> tag attributes
        number = q_el.get("number", "").strip()

        # Variable to store the body commands create by the render functions
        parts = []

        # question header
        parts.append(self.writer.question_start(number))

        # process the statement tag
        stmt = q_el.find("./statement")
        if stmt is not None:
            parts.append(self.render_statement(stmt))

        # process the options tag
        options = q_el.find("./options")
        if options is not None:
            parts.append(self.render_options(options))

        # process the options tag
        options_table = q_el.find("./options_table")
        if options_table is not None:
            parts.append(self.render_options_table(options_table))

        # process the assumptions tag
        assumptions = q_el.find("./assumptions")
        if assumptions is not None:
            parts.append(self.render_assumptions(assumptions))

        # question close
        parts.append(self.writer.question_end())

        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <statement> tag

    def render_statement(self, stmt_el) -> str:
        parts = []
        for child in stmt_el:
            parts.append(self.render_blocks(child))
        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <options> tag

    def render_options(self, options_el) -> str:
        # Variable to store the body commands create by the render functions
        parts = []

        parts.append(self.writer.options_regular_start())
        for opt in options_el.findall("./option"):
            # read the <option> tag attributes
            label = opt.get("label")  # not strictly needed, enumerate will label
            is_correct = opt.get("is_correct")

            # <option> tags can only have <p> or <image> tags
            body_parts = []
            for child in opt:
                body_parts.append(self.render_option_child(child))

            body = "\n".join([t for t in body_parts if t]).strip()
            parts.append(self.writer.options_item_start())
            parts.append(body)
            parts.append(self.writer.options_item_end())

        parts.append(self.writer.options_regular_end())

        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <options_table> tag

    def render_options_table(self, table_el) -> str:
        # check for border attribute
        table_class = table_el.get("class", None)

        # Variable to store the body commands create by the render functions
        parts = []

        # Simple table with vertical bars
        ncols = self.count_table_cols(table_el)
        parts.append(self.writer.options_table_start(ncols, table_class))

        option_index = 1

        for row in table_el:
            if row.tag == "header":
                parts.append(self.writer.options_row_start(""))
            elif row.tag == "option":
                parts.append(
                    self.writer.options_row_start(number_to_letter(option_index))
                )
                option_index += 1
            else:
                raise ValueError(
                    "Tag not recognized!" + etree.tostring(row).decode("utf-8")
                )

            for cell in row.findall("./cell"):
                align = cell.get("align")
                body_parts = []
                for sub in cell:
                    body_parts.append(self.render_option_child(sub))
                body = "\n".join([t for t in body_parts if t]).strip()

                parts.append(self.writer.options_cell_start(align))
                parts.append(body)
                parts.append(self.writer.options_cell_end())

            parts.append(self.writer.options_row_end())

        parts.append(self.writer.options_table_end())

        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <assumptions> tag

    def render_assumptions(self, assumptions_el) -> str:
        # We will render as enumerate with labels (A), (B), ...
        parts = []

        # assumptions opening
        parts.append(self.writer.assumptions_start())

        for child in assumptions_el:
            parts.append(self.render_blocks(child))

        # assumptions closing
        parts.append(self.writer.assumptions_end())

        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the statement child tags

    def render_blocks(self, el) -> str:
        tag = el.tag
        if tag == "p":
            return self.render_paragraph(el)

        elif tag == "footnote":
            return self.render_paragraph(el)

        elif tag == "header":
            return self.render_header(el)

        elif tag == "quote":
            return self.render_display_quote(el)

        elif tag == "verse":
            return self.render_verse(el)

        elif tag == "image":
            return self.render_image(el)

        elif tag == "table":
            return self.render_table(el)

        elif tag == "list":
            # symbol = el.get("symbol", None)
            return self.render_list(el)

        elif tag == "ordered_list":
            return self.render_ordered_list(el)

        elif tag == "caption":
            return self.render_caption(el)

        elif tag == "cite":
            return self.render_cite(el)
        else:
            raise ValueError("Tag not recognized!" + etree.tostring(el).decode("utf-8"))

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the statement child tags

    def render_option_child(self, el) -> str:
        tag = el.tag
        if tag == "p":
            return self.render_paragraph(el)

        elif tag == "image":
            return self.render_inline_image(el)

        else:
            raise ValueError("Tag not recognized!")

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <p> tag

    def render_paragraph(self, p_elem) -> str:
        text = self.render_inline(p_elem)
        return self.writer.paragraph(text)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <header> tag

    def render_header(self, p_elem) -> str:
        text = self.render_inline(p_elem)
        return self.writer.header(text)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <header> tag

    def render_caption(self, p_elem) -> str:
        text = self.render_inline(p_elem)
        return self.writer.caption(text)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <quote> tag

    def render_display_quote(self, q_el) -> str:
        parts = []
        parts.append(self.writer.display_quote_start())

        for child in q_el:
            if child.tag == "title":
                text = self.render_inline(child)
                parts.append(self.writer.header(text))
            elif child.tag == "p":
                parts.append(self.render_paragraph(child))
            elif child.tag == "image":
                parts.append(self.render_image(child))
            else:
                print(child)
                raise ValueError(f"Tag {child.tag} not recognized!")

        parts.append(self.writer.display_quote_end())
        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <verse> tag

    def render_verse(self, q_el) -> str:
        parts = []
        parts.append(self.writer.verse_start())

        for child in q_el:
            if child.tag == "title":
                text = self.render_inline(child)
                parts.append(self.writer.verse_title(text))

            elif child.tag == "stanza":
                parts.append(self.writer.verse_stanza_start())
                for line in child:
                    text = self.render_inline(line)
                    parts.append(self.writer.verse_line(text))
                parts.append(self.writer.verse_stanza_end())

            else:
                raise ValueError(f"Tag {child.tag} not recognized!")

        parts.append(self.writer.verse_end())
        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <image> tag

    def render_image(self, img_el) -> str:
        # get the <image> tag attributes
        src = img_el.get("src", "").strip()
        wrap = xml_to_python_boolean(img_el.get("wrap", "false").strip())
        width = img_el.get("width", "1.0").strip()
        html_width = img_el.get("html_width", "500").strip()

        # get the image path
        img_path = self.global_graphics_dir / src
        # print(img_path)
        if os.path.exists(img_path):
            print(f"xxx '{img_path}' exists (could be a file or directory).")

        return self.writer.image(img_path, wrap, width, html_width)

    #########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <image> tag
    #
    def render_inline_image(self, img_el) -> str:
        # get the <image> tag attributes
        src = img_el.get("src", "").strip()
        wrap = xml_to_python_boolean(img_el.get("wrap", "false").strip())
        width = img_el.get("width", "1.0").strip()
        html_width = img_el.get("html_width", "500").strip()

        # print(wrap, type(wrap))
        # get the image path
        img_path = self.global_graphics_dir / src

        # Use width=\linewidth to fit page
        return self.writer.inline_image(img_path, wrap, width, html_width)
        # return (
        #     "\\includegraphics[width="
        #     + width
        #     + "\\linewidth]{"
        #     + str(img_path).replace("\\", "/")
        #     + "}"
        # )

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <list> tag

    def count_table_cols(self, table_el) -> int:
        # print('###########################################################################################################')
        # print('!', etree.tostring(table_el))
        num_cols = []
        for row in table_el:
            # print('@', etree.tostring(row))

            num_cols.append(len(row.findall("./cell")))

        # def are_all_equal_all(numbers):
        if not num_cols:  # Handle empty list case
            raise ValueError("Empty row!")

        first_element = num_cols[0]
        print(num_cols)
        if all(num == first_element for num in num_cols) == False:
            for num in num_cols:
                print(num)
            print(etree.tostring(table_el))
            raise ValueError("Table with different number of columns!")

        # print(etree.tostring(table_el))
        # print('num_cols', num_cols)
        return first_element

    # def count_table_cols2(tr_el) -> int:
    #     return len(tr_el.findall("./cell"))  # + len(tr_el.findall("./th"))

    def render_table(self, table_el) -> str:
        # read the attributes for the <table> tag
        width = int(table_el.get("width", "0").strip())

        # column specification
        columns = table_el.get("columns", None)

        parts = []

        # Simple table with vertical bars
        ncols = self.count_table_cols(table_el)

        parts.append(self.writer.table_start(["c"] * ncols, width))

        for row in table_el:
            parts.append(self.writer.table_row_start())
            for index, cell in enumerate(row.findall("./cell")):
                body_parts = []
                for sub in cell:
                    body_parts.append(self.render_option_child(sub))
                body = "\n".join([t for t in body_parts if t]).strip()

                parts.append(self.writer.table_cell_start())
                # if index == 0:
                parts.append(body)
                # else:
                # parts.append(" & " + body)
                parts.append(self.writer.table_cell_end())

            parts.append(self.writer.table_row_end())

        parts.append(self.writer.table_end())

        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <list> tag

    def render_list(self, ul_el) -> str:
        symbol = ul_el.get("symbol", None)
        parts = []
        parts.append(self.writer.list_start(symbol))
        for li in ul_el.findall("./item"):
            parts.append(self.writer.list_item_start())
            # render paragraphs
            for child in li:
                if child.tag == "p":
                    parts.append(self.render_paragraph(child))

                elif child.tag == "image":
                    raise NotImplementedError("image not implemented!")

                else:
                    raise ValueError("Tag not recognized!")
            parts.append(self.writer.list_item_end())

        parts.append(self.writer.list_end())
        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <list> tag

    def render_ordered_list(self, ul_el) -> str:
        parts = []
        parts.append(self.writer.ordered_list_start())
        for li in ul_el.findall("./item"):
            parts.append(self.writer.ordered_list_item_start())
            # render paragraphs
            for child in li:
                if child.tag == "p":
                    parts.append(self.render_paragraph(child))

                elif child.tag == "image":
                    raise NotImplementedError("image not implemented!")

                else:
                    raise ValueError("Tag not recognized!")
            parts.append(self.writer.ordered_list_item_end())

        parts.append(self.writer.ordered_list_end())
        return "".join(parts)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    #  Render the <cite> tag
    #
    def render_cite(self, p_el) -> str:
        text = self.render_inline(p_el)
        return self.writer.cite(text)

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render inline elements

    def render_inline(self, p_elem) -> str:
        parts = []

        # Add text that appears directly inside <p> before first child
        if p_elem.text:
            text = self.writer.clean_text(p_elem.text)
            parts.append(text)

        # Iterate over child elements
        for child in p_elem:
            if child.tag == "b":
                text = self.render_inline(child)
                parts.append(self.writer.bold(text))

            elif child.tag == "u":
                text = self.render_inline(child)
                parts.append(self.writer.underline(text))

            elif child.tag == "i":
                text = self.render_inline(child)
                parts.append(self.writer.italic(text))

            elif child.tag == "q":
                text = self.render_inline(child)
                parts.append(self.writer.quote(text))

            elif child.tag == "style":
                color = child.get("color", "").strip()
                text = self.render_inline(child)
                parts.append(self.writer.style(text, color))

            elif child.tag == "m":
                text = self.writer.clean_math(child.text)
                parts.append(self.writer.math(text))

            elif child.tag == "math":
                end_symbol = child.get("end", "").strip()
                text = self.writer.clean_math(child.text)
                parts.append(self.writer.display_math(text, end_symbol))

            elif child.tag == "c":
                text = self.writer.clean_chemistry(child.text)
                parts.append(self.writer.chemistry(text))

            elif child.tag == "chem":
                end_symbol = child.get("end", "").strip()
                text = self.writer.clean_chemistry(child.text)
                parts.append(self.writer.display_chemistry(text, end_symbol))

            elif child.tag == "ref":
                end_symbol = child.get("id", "").strip()
                symbol = self.add_footnote(id)
                parts.append(self.writer.reference(text))

            else:
                text = self.clean_text(etree.tostring(child, encoding="unicode"))
                parts.append(text)

            # After child, add its trailing text if present
            if child.tail:
                text = self.writer.clean_text(child.tail)
                parts.append(text)

        text = "".join(parts)
        return text

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <header> tag

    def reset_footnotes(self):
        self.global_footnote_struct = {}

    def add_footnote(self, id):
        s = len(self.global_footnote_struct)
        if s >= len(FOOTNOTES_SYMBOLS):
            raise ValueError("Footnote overboard!")
        self.global_footnote_struct[id] = FOOTNOTES_SYMBOLS[s]
        return FOOTNOTES_SYMBOLS[s]

    #####1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
    # Render the <p> tag

    # def render_verse2(self, p_elem) -> str:
    #     text = self.render_inline(p_elem)
    #     end_par = "\\\\"
    #     return text + end_par


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# read_parser_arguments()


def read_parser_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument("xml", type=Path, help="Input XML file")

    parser.add_argument(
        "out",
        type=Path,
        nargs="?",
        help="Output file path (.tex or .html). "
        "If not supplied, it will be derived from input name.",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output."
    )

    parser.add_argument(
        "-p", "--print", action="store_true", help="Enable verbose output."
    )

    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument(
        "--latex", action="store_true", help="Generate LaTeX output (default)"
    )
    fmt_group.add_argument("--html", action="store_true", help="Generate HTML output")

    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("./xsd/fuvest_xml.xsd"),
        help="Path to XML Schema file (default: ./xsd/fuvest_xml.xsd)",
    )

    parser.add_argument(
        "--graphics-dir",
        type=Path,
        default=Path("../images/"),
        help="Base directory for image sources (default: ../images/)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output/"),
        help="Directory to place the output file (default: ./output/",
    )

    return parser.parse_args()


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# main()


def main():
    # Process the input arguments
    args = read_parser_arguments()

    # Decide format
    fmt = "html" if args.html else "latex"

    # Decide output filename
    if args.out is None:
        new_ext = ".html" if fmt == "html" else ".tex"
        args.out = args.output_dir / (args.xml.stem + new_ext)
    else:
        args.out = args.output_dir / args.out.name

    # Check for existence of input file
    if args.xml.is_file() is not True:
        print(f"ERROR: The file '{args.xml}' does not exists.")
        sys.exit(1)

    if fmt == "latex":
        # Processor
        xml_converter = XmlConverter(LatexWriter())

        # Store the graphics_dir path on the global variable
        xml_converter.global_graphics_dir = args.graphics_dir

        # Load the input XML and validate
        xml_converter.read_xml(args.xml)
        xml_converter.validate_xml(args.schema)

        # Create the document code
        tex = xml_converter.create_document()

        # select the console or file output
        if args.print:
            print(tex)

        else:
            args.out.write_text(tex, encoding="utf-8")
            print("Wrote LaTeX to", args.out)

    else:
        # Processor
        xml_converter = XmlConverter(HtmlWriter())

        # Store the graphics_dir path on the global variable
        xml_converter.global_graphics_dir = args.graphics_dir

        # Load the input XML and validate
        xml_converter.read_xml(args.xml)
        xml_converter.validate_xml(args.schema)

        # Create the document code
        tex = xml_converter.create_document()

        # select the console or file output
        if args.print:
            print(tex)

        else:
            args.out.write_text(tex, encoding="utf-8")
            print("Wrote LaTeX to", args.out)


if __name__ == "__main__":
    main()
