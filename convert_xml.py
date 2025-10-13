
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

import argparse
import sys
import re
from pathlib import Path
from typing import Optional, List
from lxml import etree

# Default CSS content is now stored in a constant.
DEFAULT_PREAMBLE = """\\documentclass[11pt,a4paper,twocolumn]{article}

% Packages
\\usepackage[T1]{fontenc} 	% for advanced font handling with XeLaTeX
\\usepackage[utf8]{inputenc}
\\usepackage{geometry}			% page size and margins
\\usepackage{graphicx}   	% for images
\\usepackage{wrapfig}    	% for pictures wrapingb
\\usepackage{tabularx}   	% flexible tablesbb
\\usepackage{array}      	% improved column definitions
\\usepackage{tcolorbox}  	% for boxes of text
\\usepackage{csquotes}     % for typesetting quotes
\\usepackage[version=4,textfontname=Libertinus Serif,mathfontname=Libertinus Serif]{mhchem}
\\usepackage{amsmath}
\\usepackage{mathspec}			% allow you to use open-type fonts
\\usepackage{setspace}     % for line spacing
\\usepackage{lipsum}				% for printing test

% configure the margin of the paper (geometry)
\\geometry{left=1cm,right=1cm,top=1.5cm,bottom=2cm}

% path relative to the main .tex file (graphicx)
\\graphicspath{ {./images/} }

\\raggedbottom

% configure the boxes (tcolorbox)
\\definecolor{sub}{HTML}{dedede}     % setting sub color to be used

\\newtcolorbox{assumptionBox}{
    fontupper=\\fontsize{8}{10}\\selectfont,
    colback = sub, % background color
    boxrule = 0pt  % no borders
}

% Remove indentation from quote environment
\\renewenvironment{quote}
  {\\list{}{\\leftmargin=0pt \\rightmargin=0pt}%
   \\item\\relax}
  {\\endlist}

% Define the font and size for the displayquote environment
\\newfontfamily{\\quotefont}{Libertinus Serif} % Or any other font on your system
\\renewenvironment{displayquote}{%
    \\begin{quote}
    \\fontsize{10}{12}\\selectfont % 14pt font size with 16pt line spacing
    \\quotefont
    \\setlength{\\leftskip}{1.0cm}  % Left indent of 30pt
    \\setlength{\\rightskip}{0.0cm} % Right indent of 30pt
}{%
    \\end{quote}
}

% Custom command for author formatting
\\newcommand{\\quoteauthor}[1]{%
    \\begin{flushright}
        \\vspace{-8pt}
        \\fontsize{8}{10}\\selectfont
        \\textit{\\textemdash #1}
    \\end{flushright}
}

% Set the font, size, and indent for the verse environment
\\newfontfamily{\\versefont}{Libertinus Serif} % Or any other font on your system
% Verse environment with custom style
\\newenvironment{verseblock}
  {\\list{}{\\itemsep=0pt % no extra space between items
           \\parsep=0pt
           \\leftmargin=1.0cm  % left indent
           \\rightmargin=0.0cm % right indent
           \\fontsize{10}{12}\\selectfont
		\\versefont\\itshape}%
   \\item\\relax}
  {\\endlist}

\\renewcommand{\\thesection}{\\huge\\arabic{section}.}
\\renewcommand{\\theenumi}{\\Alph{enumi}}
\\renewcommand\\labelenumi{(\\theenumi)}


% set the document fonts (mathspec)
\\setmainfont{Libertinus Serif}
\\setmathfont(Digits,Latin)[Scale=MatchLowercase]{Libertinus Serif}

\\setlength\\parindent{0pt}   % killing indentation for all the text
\\setstretch{1.1}            % setting line spacing
\\setlength\\columnsep{1.0cm} % setting length of column separator
\\pagestyle{empty}           % setting pagestyle to be empty

\\newcommand{\\lt}{<}
\\newcommand{\\gt}{>}

"""

# Global variable
global_graphics_dir = None
global_footnote_struct = {}

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag

FOOTNOTES_SYMBOLS = [
    '*',
    '**',
    '***',
    '****',
    '*****',
]

def reset_footnotes():
    global global_footnote_struct
    global_footnote_struct = {}

def add_footnote(id):
    global global_footnote_struct
    s = len(global_footnote_struct)
    if s >= len(FOOTNOTES_SYMBOLS):
        raise ValueError("Footnote overboard!")
    global_footnote_struct[id] = FOOTNOTES_SYMBOLS[s]
    return FOOTNOTES_SYMBOLS[s]

# --- LaTeX helpers ---

# LATEX_SPECIALS = {
#     "&": r"\&",
#     "%": r"\%",
#     "#": r"\#",
#     "_": r"\_",
#     "{": r"\{",
#     "}": r"\}",
#     "~": r"\textasciitilde{}",
#     "^": r"\textasciicircum{}",
#     "\\": r"\textbackslash{}",
# }

# def escape_latex(text: str) -> str:
#     """Escape LaTeX special chars but **leave $ intact** to preserve math already provided in the XML."""
#     if not text:
#         return ""
#     # First, we might want to preserve verbatim $...$ math by splitting on $ pairs
#     # But that's fragile; better: just do not escape '$' at all.
#     # Also normalize Windows newlines
#     text = text.replace("\r\n", "\n")
#     # Replace special characters
#     out = []
#     for ch in text:
#         if ch in LATEX_SPECIALS:
#             out.append(LATEX_SPECIALS[ch])
#         else:
#             out.append(ch)
#     return "".join(out)

# def strip_md_italics(text: str) -> str:
#     """If the whole text is wrapped in underscores like _foo_, trim those underscores."""
#     if text is None:
#         return ""
#     stripped = text.strip()
#     if len(stripped) >= 2 and stripped[0] == "_" and stripped[-1] == "_":
#         return stripped[1:-1].strip()
#     return stripped
#
#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag
#
def clean_text(text: str) -> str:
    # Dictionary of characters to escape
    escape_map = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '→': r'->',
        '⇌': r'<=>',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
    }

    # Create a regex from the keys of the map
    escape_regex = re.compile('|'.join(map(re.escape, escape_map.keys())))

    # Perform the replacement
    fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

    return fully_escaped_text

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag
#
def clean_chemistry(text: str) -> str:
    #print("#", text)
    # Dictionary of characters to escape
    escape_map = {
        'α': r'\alpha',
        '→': r'->',
        '⇌': r'<=>',
    }

    # Create a regex from the keys of the map
    escape_regex = re.compile('|'.join(map(re.escape, escape_map.keys())))

    # Perform the replacement
    fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

    return fully_escaped_text

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag
#
def clean_math(text: str) -> str:
    #print("#", text)
    # Dictionary of characters to escape
    escape_map = {
        'π': r'\pi',
    }

    # Create a regex from the keys of the map
    escape_regex = re.compile('|'.join(map(re.escape, escape_map.keys())))

    # Perform the replacement
    fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], text)

    return fully_escaped_text

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag
#
def read_xml(xml_path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=True)
    return etree.parse(str(xml_path), parser)

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag
#
def validate_xml(doc: etree._ElementTree, xsd_path: Path) -> None:
    xmlschema_doc = etree.parse(str(xsd_path))
    xmlschema = etree.XMLSchema(xmlschema_doc)
    if not xmlschema.validate(doc):
        log = xmlschema.error_log
        # Build a readable error message
        messages = ["XML does not conform to the provided XSD schema:"]
        for e in log:
            messages.append(f"  Line {e.line}, Col {e.column}: {e.message}")
        raise ValueError("\n".join(messages))

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <header> tag

def render_header(p_elem) -> str:

    text = render_inline(p_elem)
    return f"\\textbf{{{text}}}\n\n"

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <p> tag

def render_paragraph(p_elem, inline=False) -> str:

    text = render_inline(p_elem)
    end_par = "\n\n" if inline == False else "\\\\"

    return text + end_par

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render inline elements

def render_inline(p_elem) -> str:

    parts = []

    # Add text that appears directly inside <p> before first child
    if p_elem.text:
        text = clean_text(p_elem.text)
        parts.append(text)

    # Iterate over child elements
    for child in p_elem:
        if child.tag == "b":
            text = render_inline(child)
            parts.append(f"\\textbf{{{text}}}")
        elif child.tag == "u":
            text = render_inline(child)
            parts.append(f"\\underline{{{text}}}")
        elif child.tag == "i":
            text = render_inline(child)
            parts.append(f"\\textit{{{text}}}")
        elif child.tag == "q":
            text = render_inline(child)
            parts.append(f"“{text}”")
        elif child.tag == "m":
            text = clean_math(child.text)
            parts.append(f"${text}$")
        elif child.tag == "math":
            end_symbol = child.get("end", "").strip()
            text = clean_math(child.text)
            parts.append(f"\n$${text} {end_symbol}$$\n")
        elif child.tag == "c":
            text = clean_chemistry(child.text)
            parts.append(f"\\ce{{{text}}}")
        elif child.tag == "chem":
            text = clean_chemistry(child.text)
            parts.append(f"$$\\ce{{{text}}}$$")
        elif child.tag == "ref":
            end_symbol = child.get("id", "").strip()
            symbol = add_footnote(id)
            parts.append(f"$^{{\mathrm{{{symbol}}} }}$")
        else:
            text = clean_text(etree.tostring(child, encoding='unicode'))
            parts.append(text)

        # After child, add its trailing text if present
        if child.tail:
            text = clean_text(child.tail)
            parts.append(text)

    text = "".join(parts)
    return text

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
#  Render the <cite> tag
#
def render_cite(p_el) -> str:
    text = "".join(p_el.itertext()).strip()
    return "\\quoteauthor{" + clean_text(text) + "}\n\n"

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <quote> tag
#
# Example:
#        \begin{quote}
#            Paris is the capital and most populous city of France. It is an important center for art, fashion, gastronomy, and culture.
#            The city is known as the ‘City of Light’ due to its leading role during the Age of Enlightenment and its early adoption of street lighting.
#            \quoteauthor{Encyclopedia Britannica}
#        \end{quote}

def render_quote(q_el) -> str:
    parts = []
    parts.append("\\begin{displayquote}\n")

    inner_ps = q_el.findall("./p")
    if inner_ps:
        for p in inner_ps:
            parts.append(render_paragraph(p))

    # author_el = q_el.find("./author")
    # if author_el is not None and (author_el.text or "").strip():
    #     author = strip_md_italics(author_el.text or "")
    #     #parts.append("\\begin{flushright}\\textit{" + escape_latex(author) + "}\\end{flushright}\n")
    #     parts.append("\\quoteauthor{" + escape_latex(author) + "}\n")

    parts.append("\\end{displayquote}\n")
    parts.append("\n")
    return "".join(parts)

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <verse> tag

def render_verse(q_el) -> str:
    parts = []
    parts.append("\\begin{verseblock}\n")

    for child in q_el:
        if child.tag == "title":
            text = render_inline(child)
            parts.append("\\textbf{" + text + "}\\\\\n")
        elif child.tag == "p":
            text = render_inline(child)
            parts.append(text + "\\\\\n")
        else:
            raise ValueError("Tag not recognized!")

    parts.append("\\end{verseblock}\n")
    parts.append("\n")
    return "".join(parts)

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

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <image> tag

def render_image(img_el) -> str:
     # get the <image> tag attributes
    src = img_el.get("src", "").strip()
    pos = img_el.get("position", "").strip()
    size = img_el.get("size", "").strip()
    wrap = xml_to_python_boolean(img_el.get("wrap", "false").strip())
    width = img_el.get("width", "1.0").strip()

    # get the image path
    img_path = global_graphics_dir / src

    parts = []
    if wrap is True:
        parts.append("\\begin{wrapfigure}{l}[0pt]{" + width + "\\linewidth}\n")
        parts.append("\\centering\n")
        parts.append("\\includegraphics[width=" + size + "]{" + str(img_path).replace('\\','/') + "}\n")
        parts.append("\\end{wrapfigure}\n\n")
    else:
        parts.append("\\begin{center}\n")
        parts.append("\\includegraphics[width=" + width + "\\linewidth]{" + str(img_path).replace('\\','/') + "}\n")
        parts.append("\\end{center}\n\n")

    return "".join(parts)

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <image> tag
#
def render_inline_image(img_el) -> str:
    # get the <image> tag attributes
    src = img_el.get("src", "").strip()
    pos = img_el.get("position", "").strip()
    size = img_el.get("size", "").strip()
    wrap = xml_to_python_boolean(img_el.get("wrap", "false").strip())
    width = img_el.get("width", "1.0").strip()

    #print(wrap, type(wrap))
    # get the image path
    img_path = global_graphics_dir / src

    # Use width=\linewidth to fit page
    return "\\includegraphics[width=" + width + "\\linewidth]{" + str(img_path).replace('\\','/') + "}"


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <list> tag

def count_table_cols(table_el) -> int:
    #print('###########################################################################################################')
    #print('!', etree.tostring(table_el))
    num_cols = []
    for row in table_el:
        #print('@', etree.tostring(row))

        num_cols.append(len(row.findall("./cell")))

    #def are_all_equal_all(numbers):
    if not num_cols:  # Handle empty list case
        raise ValueError("Empty row!")

    first_element = num_cols[0]
    print(num_cols)
    if all(num == first_element for num in num_cols) == False:
        for num in num_cols:
            print(num)
        print(etree.tostring(table_el))
        raise ValueError("Table with different number of columns!")

    #print(etree.tostring(table_el))
    #print('num_cols', num_cols)
    return first_element

def render_table(table_el) -> str:
    # read the attributes for the <table> tag
    width = int(table_el.get("width", "0").strip())
    columns = table_el.get("columns", None)

    parts = []

    # Simple table with vertical bars
    ncols = count_table_cols(table_el)


    if columns is not None:
        columns_split = columns.strip().split()
        if len(columns_split) != ncols:
            raise ValueError("Number of columns is diferent than ncols")
        colspec = "|".join(columns_split)
    else:
        colspec = "|".join(["c"] * ncols)

    parts.append("\\begin{center}\n")
    if width == 0:
        parts.append("\\begin{tabular}{|" + colspec + "|}\n")
    else:
        width_str = f"{width / 100.0:.2f}"
        parts.append("\\begin{tabularx}{" + width_str + "\\linewidth}{|" + colspec + "|}\n")
    parts.append("\\hline\n")

    for row in table_el:
        for index, cell in enumerate(row.findall("./cell")):
            body_parts = []
            for sub in cell:
                body_parts.append(render_option_child(sub))
            body = "\n".join([t for t in body_parts if t]).strip()

            if index == 0:
                parts.append(body)
            else:
                parts.append(" & " + body)

        parts.append(" \\\\\n")
        parts.append("\\hline\n")

    if width == 0:
        parts.append("\\end{tabular}\n")
    else:
        parts.append("\\end{tabularx}\n")
    parts.append("\\end{center}\n\n")

    return "".join(parts)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <list> tag

def render_list(ul_el) -> str:
    parts = []
    parts.append("\\begin{itemize}\n")
    for li in ul_el.findall("./item"):
        #txt = "".join(li.itertext()).strip()
        # parts.append(render_paragraph(p))
        print(li, dir(li))
        parts.append("\\item ")
        # render paragrphs
        for child in li:
            if child.tag == "p":
                #print("bold", p_elem.text)
                parts.append(render_paragraph(child))
            elif child.tag == "image":
                raise NotImplementedError("image not implemented!")
            else:
                raise ValueError("Tag not recognized!")
        #parts.append("\\item " + render_paragraph(li.child) + "\n")
        #parts.append("\n")
    parts.append("\\end{itemize}\n\n")
    return "".join(parts)


def count_table_cols2(tr_el) -> int:
    return len(tr_el.findall("./cell")) # + len(tr_el.findall("./th"))


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <assumptions> tag

def render_assumptions(assumptions_el) -> str:
    # We will render as enumerate with labels (A), (B), ...
    parts = []

    parts.append("\\begin{assumptionBox}\n")
    parts.append("\\textit{Note e adote:}\n\n")
    for child in assumptions_el:
        parts.append(render_statement_child(child))
    parts.append("\\end{assumptionBox}\n")

    return "".join(parts)

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# number_to_letter auxiliar function

def number_to_letter(number):
  """
  Converts an integer (1-26) to its corresponding uppercase letter (A-Z).

  Args:
    number: An integer between 1 and 26 (inclusive).

  Returns:
    The corresponding uppercase letter, or a ValueError if the input is out of range.
  """
  if not 1 <= number <= 26:
    raise ValueError("Input number must be between 1 and 26.")
  return chr(64 + number)

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the options tag
#
def render_options(options_el) -> str:
    # We will render as enumerate with labels (A), (B), ...
    parts = []

    # check for a <table> tag
    table_el = options_el.find("./table")

    # It is a table options
    if table_el is not None:
        # Simple table with vertical bars
        ncols = count_table_cols(table_el)
        colspec = "|".join(["X"] * ncols)

        parts.append("\\begin{center}\n")
        parts.append("\\begin{tabularx}{\\linewidth}{|c|" + colspec + "|}\n")
        parts.append("\\hline\n")

        option_index = 1

        for row in table_el:
            if row.tag == "option":
                parts.append(f" ({number_to_letter(option_index)}) ")
                option_index += 1

            for cell in row.findall("./cell"):
                body_parts = []
                for sub in cell:
                    body_parts.append(render_option_child(sub))
                body = "\n".join([t for t in body_parts if t]).strip()

                parts.append(" & " + body)

            parts.append("\\\\\n")
            parts.append("\\hline\n")

        parts.append("\\end{tabularx}\n")
        parts.append("\\end{center}\n\n")

    # the options are not a table options
    else:
        parts.append("\\begin{enumerate}\n")
        for opt in options_el.findall("./option"):
            # read the <option> tag attributes
            label = opt.get("label")  # not strictly needed, enumerate will label
            is_correct = opt.get("is_correct")

            # <option> tags can only have <p> or <image> tags
            body_parts = []
            for child in opt:
                body_parts.append(render_option_child(child))

            body = "\n".join([t for t in body_parts if t]).strip()
            parts.append("\\item " + body + "\n")

        parts.append("\\end{enumerate}\n\n")

    return "".join(parts)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the statement child tags

def render_option_child(el) -> str:
    tag = el.tag
    if tag == "p":
        return render_paragraph(el)
    elif tag == "image":
        return render_inline_image(el)
    else:
        raise ValueError("Tag not recognized!")


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the statement child tags

def render_statement_child(el) -> str:
    tag = el.tag
    if tag == "p":
        return render_paragraph(el)
    elif tag == "footnote":
        return render_paragraph(el)
    elif tag == "header":
        return render_header(el)
    elif tag == "quote":
        return render_quote(el)
    elif tag == "verse":
        return render_verse(el)
    elif tag == "image":
        return render_image(el)
    elif tag == "table":
        return render_table(el)
    elif tag == "list":
        return render_list(el)
    elif tag == "caption":
        return render_header(el)
    elif tag == "cite":
        return render_cite(el)
    else:
        raise ValueError("Tag not recognized!" + etree.tostring(el).decode('utf-8'))


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <statement> tag

def render_statement(stmt_el) -> str:
    parts = []
    for child in stmt_el:
        parts.append(render_statement_child(child))
    return "".join(parts)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <objective_question> tag

def render_objective_question(q_el):

    # get the <objective_question> tag attributes
    number = q_el.get("number", "").strip()

    # header
    header = "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n"
    header += f"% Question {number}\n\n"
    header += "\\section{}\n"

    parts = [header + "\n"]

    # process the statement tag
    stmt = q_el.find("./statement")
    if stmt is not None:
        parts.append(render_statement(stmt))

    # process the options tag
    options = q_el.find("./options")
    if options is not None:
        parts.append(render_options(options))

    assumptions = q_el.find("./assumptions")
    if assumptions is not None:
        parts.append(render_assumptions(assumptions))

    parts.append("\\centerline{\\rule{5cm}{0.5pt}}\n\n")

    return "".join(parts)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <context> tag

def render_context(ctx_el, num_questions=1, min_question=0, max_question=0) -> str:
    parts = []
    parts.append("\\vspace{18pt}\n\n")

    if num_questions == 1:
        parts.append("\\begin{center}\n")
        parts.append(f"\\textbf{{TEXTO PARA A QUESTÃO {min_question}}}\n")
        parts.append("\\end{center}\n\n")
    elif num_questions == 2:
        parts.append("\\begin{center}\n")
        parts.append(f"\\textbf{{TEXTO PARA AS QUESTÕES {min_question} E {max_question}}}\n")
        parts.append("\\end{center}\n\n")
    elif num_questions > 2:
        parts.append("\\begin{center}\n")
        parts.append(f"\\textbf{{TEXTO PARA AS QUESTÕES DE {min_question} A {max_question}}}\n")
        parts.append("\\end{center}\n\n")

    # context may contain paragraphs and other elements
    for child in ctx_el:
        parts.append(render_statement_child(child))
    return "".join(parts)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# create_latex()

def create_latex(doc: etree._ElementTree) -> str:
    root = doc.getroot()
    name = root.get("name", "Exam")
    year = root.get("year", "")
    phase = root.get("phase", "")
    day = root.get("day", "")
    variation = root.get("variation", "")

    # Header
    preamble = [DEFAULT_PREAMBLE]

    title_line = f"{clean_text(name)}"
    #subtitle = " ".join(filter(None, [markdown_to_latex(phase), markdown_to_latex(day), markdown_to_latex(variation)]))
    title_full = title_line #+ (f" --- {subtitle}" if subtitle else "")

    preamble.append("\\title{\\textbf{" + title_full + "}}\n")
    preamble.append("\\date{}\n")
    preamble.append("\\author{}\n")
    preamble.append("\n")
    preamble.append("\\begin{document}\n\n\\maketitle\n\n")

    # Variable to store the body commands create by the render functions
    body = []

    # Inner function to process question_groups tags
    def process_question_group(parent):

        # reset the footnote structure
        reset_footnotes()

        obj_questions = parent.findall("./objective_question")
        min_question=1000
        max_question=0
        if len(obj_questions) > 1:
            #print(len(obj_questions))
            for q in obj_questions:
                number = int(q.get("number", "").strip())
                min_question = min_question if number > min_question else number
                max_question = max_question if number < max_question else number

        for child in parent:
            if child.tag == "context":
                body.append(render_context(child, len(obj_questions), min_question, max_question))
            elif child.tag == "objective_question":
                body.append(render_objective_question(child))
            elif child.tag == "discursive_question":
                raise NotImplementedError("discursive_question not implemented!")
            else:
                raise ValueError("Tag not recognized!")

    # Iterate over the exam child tags
    for child in root:
        if child.tag == "subject":
            for sub_child in child:
                process_question_group(sub_child)

        elif child.tag == "question_group":
            process_question_group(child)

        else:
            raise ValueError("Tag not recognized!")

    # Ending
    ending = []
    ending.append("\\end{document}\n")

    return "".join(preamble + body + ending)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# read_parser_arguments()

def read_parser_arguments():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path, help="Input XML file")
    ap.add_argument("out", type=Path, nargs="?", help="Output file path (.tex or .html). "
                                                     "If not supplied, it will be derived from input name.")

    fmt_group = ap.add_mutually_exclusive_group()
    fmt_group.add_argument("--latex", action="store_true", help="Generate LaTeX output (default)")
    fmt_group.add_argument("--html", action="store_true", help="Generate HTML output")

    ap.add_argument("--schema", type=Path, default=Path("./xsd/fuvest_xml.xsd"),
                    help="Path to XML Schema file (default: ./xsd/fuvest_xml.xsd)")
    ap.add_argument("--graphics-dir", type=Path, default=Path("../images/"),
                    help="Base directory for image sources (default: ../images/)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output/"),
                    help="Directory to place the output file (default: ./output/")

    return ap.parse_args()


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# main()

def main():

    # Declare intent to modify the global variable
    global global_graphics_dir

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

    # Store the graphics_dir path on the global variable
    global_graphics_dir = args.graphics_dir

    # Check for existence of input file
    if args.xml.is_file() is not True:
        print(f"ERROR: The file '{args.xml}' does not exists.")
        sys.exit(1)

    # Load the input XML and validate
    xml_input = read_xml(args.xml)
    validate_xml(xml_input, args.schema)

    if fmt == "latex":
        tex = create_latex(xml_input)
        args.out.write_text(tex, encoding="utf-8")
        print("Wrote LaTeX to", args.out)
    else:
        raise NotImplementedError("html output not implemented!")


if __name__ == "__main__":
    main()
