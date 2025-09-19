
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
\\usepackage{wrapfig}    	% for pictures wraping
\\usepackage{tabularx}   	% flexible tables
\\usepackage{array}      	% improved column definitions
\\usepackage{tcolorbox}  	% for boxes of text
\\usepackage{csquotes}     % for typesetting quotes
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
		\\versefont\itshape}%
   \\item\\relax}
  {\\endlist}

\\renewcommand{\\thesection}{\\huge\\arabic{section}.}
\\renewcommand{\\theenumi}{\\Alph{enumi}}
\\renewcommand\\labelenumi{(\\theenumi)}


% set the document fonts (mathspec)
\\setmainfont{Libertinus Serif}
\\setmathfont(Digits,Latin)[Scale=MatchLowercase]{Libertinus Serif}

\\setlength\parindent{0pt}   % killing indentation for all the text
\\setstretch{1.1}            % setting line spacing
\\setlength\columnsep{1.0cm} % setting length of column separator
\\pagestyle{empty}           % setting pagestyle to be empty

\\newcommand{\lt}{<}
\\newcommand{\gt}{>}

"""



# Global variable
global_graphics_dir = None


import re

# To handle nested emphasis like **_bold italic_** → \textbf{\textit{...}}, we need to be more careful.

# Instead of a single regex pass, we can apply ordered substitutions that allow nesting. The trick is to convert the inner (* or _ italics) before the outer (** or __ bold). That way, when bold wraps around an italic segment, LaTeX nesting is preserved.

# Here’s the improved function:

def convert_quotes_to_latex(input_string):
    """
    Replaces standard double quotes (") in a string with LaTeX-style
    double quotes ('' and ´´) based on their context.

    An opening quote is assumed to be a `"` followed by an alphanumeric
    character. A closing quote is assumed to be a `"` that follows an
    alphanumeric character or a punctuation mark.

    Args:
        input_string: The string containing standard double quotes to be converted.

    Returns:
        A new string with the double quotes replaced by their LaTeX equivalents.
    """
    # Replace opening quotes: " followed by a word character (alphanumeric/underscore).
    # This uses a positive lookahead `(?=\w)` to match a quote that is
    # followed by a word character without including it in the match.
    temp_string = re.sub(r'"(?=\w)', "``", input_string)

    # Replace closing quotes: a word character or punctuation followed by ".
    # This uses a positive lookbehind `(?<=\w|[.,?!;:])` to match a quote
    # that is preceded by a word/punctuation character without including it.
    final_string = re.sub(r'(?<=\w|[.,?!;:])"', "''", temp_string)
    
    return final_string
    
    
def markdown_to_latex(text: str) -> str:
    """
    Converts a Markdown-formatted string to a LaTeX-formatted string.

    This function handles:
    - Strong emphasis: **text** or __text__ becomes \\textbf{text}
    - Emphasis: *text* or _text_ becomes \\textit{text}
    - Underline: <u>text</u> becomes \\underline{text}
    - Math environments: $...$ and $$...$$ are preserved.
    - Escaping of special LaTeX characters (&, %, $, #, _, {, }, ~, ^, \\) 
      outside of math environments.

    Args:
        text: The input string formatted in Markdown.

    Returns:
        A string formatted for use in a LaTeX document.
    """
    if not text:
        return ""
        
    #print('######################################################################################')
    #print('1', text)

    # --- 1. Protect Math Environments ---
    # We find all math blocks, replace them with a unique placeholder,
    # and store the original math content to be restored later. This prevents
    # the special characters inside math from being escaped.
    math_placeholders = []
    def _replace_math_with_placeholder(match):
        math_content = match.group(0)
        # Use a placeholder that contains no special LaTeX characters.
        placeholder = f"MATHPLACEHOLDER{len(math_placeholders)}"
        math_placeholders.append(math_content)
        return placeholder

    # Replace both inline ($...$) and display ($$...$$) math blocks.
    # The DOTALL flag allows '.' to match newlines within display math.
    text_no_math = re.sub(r'\$\$.*?\$\$|\$.*?\$', _replace_math_with_placeholder, text, flags=re.DOTALL)
    #print(text_no_math)
    
    # process que inline quotes
    # list_words = text_no_math.split()
    # for word in list_words:
        # if word.startswith('"'):
    
    #print('2', text_no_math)


    # TODO: --
    
    # --- 2. Convert Markdown to LaTeX ---
    # The order of these replacements is crucial. We parse from the longest,
    # most specific markers (like ***) to the shortest, least specific (*).
    # This prevents parts of a larger marker from being incorrectly matched.
    processed_text = convert_quotes_to_latex(text_no_math)
    
    # Bold and Italic (e.g., ***text*** or ___text___)
    processed_text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\\textbf{\\textit{\1}}', processed_text, flags=re.DOTALL)
    processed_text = re.sub(r'___(.+?)___', r'\\textbf{\\underline{\1}}', processed_text, flags=re.DOTALL)

    # Strong emphasis (bold)
    processed_text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', processed_text, flags=re.DOTALL)
    processed_text = re.sub(r'__(.+?)__', r'\\underline{\1}', processed_text, flags=re.DOTALL)
    
    # Emphasis (italic)
    processed_text = re.sub(r'\*(.+?)\*', r'\\textit{\1}', processed_text, flags=re.DOTALL)
    processed_text = re.sub(r'_(.+?)_', r'\\textit{\1}', processed_text, flags=re.DOTALL)
    
    #print('3', processed_text)

    # Underline (using a common HTML-like convention)
    processed_text = re.sub(r'<u>(.*?)</u>', r'\\underline{\1}', processed_text, flags=re.DOTALL)


    # --- 3. Escape Remaining Special LaTeX Characters ---
    # Now that Markdown is converted, any remaining special characters must be escaped
    # so they are displayed literally in LaTeX. We must be careful not to escape
    # the backslashes in the LaTeX commands we just added (e.g., in `\textbf`).
    
    # Temporarily protect the LaTeX commands we've just created.
    latex_command_placeholders = []
    def _replace_latex_command_with_placeholder(match):
        command = match.group(0)
        # Use a placeholder that contains no special LaTeX characters.
        placeholder = f"LATEXCOMMANDHOLDER{len(latex_command_placeholders)}"
        latex_command_placeholders.append(command)
        return placeholder
        
    # NOTE: This regex for capturing command blocks is simple and will fail on
    # deeply nested commands (e.g., `\textbf{some {nested} text}`). However, the
    # markdown conversion above does not produce such structures.
    processed_text = re.sub(r'\\(textbf|textit|underline)\{.*?\}', _replace_latex_command_with_placeholder, processed_text, flags=re.DOTALL)

    # Dictionary of characters to escape
    escape_map = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
    }
    
    # Create a regex from the keys of the map
    escape_regex = re.compile('|'.join(map(re.escape, escape_map.keys())))
    
    # Perform the replacement
    fully_escaped_text = escape_regex.sub(lambda mo: escape_map[mo.group(0)], processed_text)

    # --- 4. Restore All Placeholders ---
    # Restore the protected LaTeX commands first.
    for i, command in reversed(list(enumerate(latex_command_placeholders))):
        placeholder = f"LATEXCOMMANDHOLDER{i}"
        fully_escaped_text = fully_escaped_text.replace(placeholder, command)

    #print(math_placeholders)
    
    # Restore the protected math content.
    for i, math_content in reversed(list(enumerate(math_placeholders))):
        placeholder = f"MATHPLACEHOLDER{i}"
        fully_escaped_text = fully_escaped_text.replace(placeholder, math_content)

    return fully_escaped_text
    
    
    

def markdown_to_latex2(md: str) -> str:
    """Convert Markdown-formatted text to LaTeX, with nested * / _ emphasis and math support."""

    #print('######################################################################################')
    #print('1', md)
    
    # --- Step 1: Temporarily protect math ($...$, $$...$$) ---
    math_blocks = {}

    def protect_math(match):
        key = f"__MATHBLOCK{len(math_blocks)}__"
        math_blocks[key] = match.group(0)
        return key

    protected = re.sub(r"\$\$.*?\$\$", protect_math, md, flags=re.DOTALL)
    protected = re.sub(r"\$[^$]+\$", protect_math, protected)

    tex = protected

    #print('2', tex)
    
    # --- Step 2: Headings ---
    # tex = re.sub(r"^###### (.+)$", "\\subsubsubsection{\\1}", tex, flags=re.MULTILINE)
    # tex = re.sub(r"^##### (.+)$", "\\paragraph{\\1}", tex, flags=re.MULTILINE)
    # tex = re.sub(r"^#### (.+)$", "\\subsubsection{\\1}", tex, flags=re.MULTILINE)
    # tex = re.sub(r"^### (.+)$", "\\subsection{\\1}", tex, flags=re.MULTILINE)
    # tex = re.sub(r"^## (.+)$", "\\section{\\1}", tex, flags=re.MULTILINE)
    # tex = re.sub(r"^# (.+)$", "\\section*{\\1}", tex, flags=re.MULTILINE)

    # --- Step 3: Emphasis (ordered for nesting) ---
    # Italics (*...* or _..._)
    tex = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", "\\textit{\\1}", tex)
    #tex = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", "\\textit{\\1}", tex)

    # Bold (**...** or __...__)
    #tex = re.sub(r"\*\*(.+?)\*\*", "\textbf{\1}", tex)
    #tex = re.sub(r"__(.+?)__", "\textbf{\1}", tex)

    # Inline code
    #tex = re.sub(r"`([^`]+)`", "\texttt{\1}", tex)
    
    #print('3', tex)

    # Links and images
    # tex = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", "\\includegraphics[width=0.6\\linewidth]{\\2}", tex)
    # tex = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", "\\href{\\2}{\\1}", tex)

    # Blockquotes
    # tex = re.sub(r"^> (.+)$", "\\begin{quote}\\1\\end{quote}", tex, flags=re.MULTILINE)

    # --- Step 4: Lists ---
    def convert_list(match):
        items = match.group(0).strip().splitlines()
        latex_items = ["\\item " + re.sub(r"^[-*+] ", "", item).strip() for item in items]
        return "\\begin{itemize}\n" + "\n".join(latex_items) + "\n\\end{itemize}"

    tex = re.sub(r"((?:^[-*+] .+\n?)+)", convert_list, tex, flags=re.MULTILINE)

    def convert_enum(match):
        items = match.group(0).strip().splitlines()
        latex_items = ["\\item " + re.sub(r"^\d+\. ", "", item).strip() for item in items]
        return "\\begin{enumerate}\n" + "\n".join(latex_items) + "\n\\end{enumerate}"

    tex = re.sub(r"((?:^\d+\. .+\n?)+)", convert_enum, tex, flags=re.MULTILINE)

    # --- Step 5: Restore math ---
    for key, val in math_blocks.items():
        tex = tex.replace(key, val)

    return tex




def read_xml(xml_path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=True)
    return etree.parse(str(xml_path), parser)

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

# --- LaTeX helpers ---

LATEX_SPECIALS = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

def escape_latex(text: str) -> str:
    """Escape LaTeX special chars but **leave $ intact** to preserve math already provided in the XML."""
    if not text:
        return ""
    # First, we might want to preserve verbatim $...$ math by splitting on $ pairs
    # But that's fragile; better: just do not escape '$' at all.
    # Also normalize Windows newlines
    text = text.replace("\r\n", "\n")
    # Replace special characters
    out = []
    for ch in text:
        if ch in LATEX_SPECIALS:
            out.append(LATEX_SPECIALS[ch])
        else:
            out.append(ch)
    return "".join(out)

def strip_md_italics(text: str) -> str:
    """If the whole text is wrapped in underscores like _foo_, trim those underscores."""
    if text is None:
        return ""
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == "_" and stripped[-1] == "_":
        return stripped[1:-1].strip()
    return stripped


#########################################################################################################################
# Render the <header> tag

def render_header(header_el) -> str:
    text = "".join(header_el.itertext()).strip()
    #print('0', text)
    #return markdown_to_latex(escape_latex(text)) + "\n\n"
    return "\\textbf{" + markdown_to_latex(text) + "}\n\n"
    
#########################################################################################################################
# Render the <p> tag

def render_paragraph(p_el) -> str:
    # https://www.overleaf.com/learn/latex/Typesetting_quotations
    # Text, ``text in English double quotes'', `text in English single quotes'.
    # https://www.reddit.com/r/LaTeX/comments/11crv0h/problems_with_the_quotation_marks/
    # For single quotes:
# Use a single backtick (`) for the opening quote.
# Use a single apostrophe (') for the closing quote.
# Example: `This is a single quote.'
# For double quotes:
# Use two backticks (``) for the opening quote.
# Use two apostrophes ('') for the closing quote.
# Example: ``This is a double quote.''

    #print('teste', list(p_el.itertext()))
    text = "".join(p_el.itertext()).strip()
    #print('0', text)
    #return markdown_to_latex(escape_latex(text)) + "\n\n"
    return markdown_to_latex(text) + "\n\n"

def render_inline_paragraph(p_el) -> str:
    text = "".join(p_el.itertext()).strip()
    return markdown_to_latex(text)


def render_cite(p_el) -> str:
    text = "".join(p_el.itertext()).strip()
    return "\\quoteauthor{" + markdown_to_latex(text) + "}\n\n"

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
        
    author_el = q_el.find("./author")
    if author_el is not None and (author_el.text or "").strip():
        author = strip_md_italics(author_el.text or "")
        #parts.append("\\begin{flushright}\\textit{" + escape_latex(author) + "}\\end{flushright}\n")
        parts.append("\\quoteauthor{" + escape_latex(author) + "}\n")
    
    parts.append("\\end{displayquote}\n")
    parts.append("\n")
    return "".join(parts)

#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# Render the <verse> tag

def render_verse(q_el) -> str:
    parts = []
    parts.append("\\begin{verseblock}\n")
    
    header_ps = q_el.find("./header")
    if header_ps is not None:
        text = "".join(header_ps.itertext()).strip()
        parts.append(markdown_to_latex(text) + "\\\\\n")
    
    inner_ps = q_el.findall("./p")
    if inner_ps:   
        for p in inner_ps:
            text = "".join(p.itertext()).strip()
            parts.append(markdown_to_latex(text) + "\\\\\n")
        
    author_el = q_el.find("./author")
    if author_el is not None and (author_el.text or "").strip():
        author = strip_md_italics(author_el.text or "")
        #parts.append("\\begin{flushright}\\textit{" + escape_latex(author) + "}\\end{flushright}\n")
        parts.append("\\quoteauthor{" + escape_latex(author) + "}\n")
    
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
    
def render_image(img_el) -> str:
     # get the <image> tag attributes
    src = img_el.get("src", "").strip()
    pos = img_el.get("position", "").strip()
    size = img_el.get("size", "").strip()
    wrap = xml_to_python_boolean(img_el.get("wrap", "false").strip())
    width = img_el.get("width", "1.0").strip()

    
    #print(wrap, type(wrap))
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
    for li in ul_el.findall("./li"):
        txt = "".join(li.itertext()).strip()
        parts.append("\\item " + markdown_to_latex(txt) + "\n")
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
# Render the options tag

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
        return render_inline_paragraph(el)
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
    elif tag == "ul":
        return render_list(el)
    elif tag == "caption":
        return render_header(el)
    elif tag == "cite":
        return render_cite(el)
    else:
        raise ValueError("Tag not recognized!" + etree.tostring(el).decode('utf-8'))


#########################################################################################################################
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
    
    title_line = f"{markdown_to_latex(name)}"
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

    # Context blocks can appear as siblings to question_group, handle flexibly
    for child in root:       
        if child.tag == "subject":
            for sub_child in child:
                process_question_group(sub_child)
            
        elif child.tag == "question_group":
            process_question_group(child)

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
