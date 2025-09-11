
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
DEFAULT_PREAMBLE = """\\documentclass[10pt,a4paper]{exam}

% Encoding
\\usepackage[T1]{fontenc}
\\usepackage[utf8]{inputenc}

% Packages
\\usepackage{multicol}   % two-column layout
\\usepackage{tabularx}   % flexible tables
\\usepackage{array}      % improved column definitions
\\usepackage{verse}
%\\usepackage[threshold=0]{csquotes}
%\\SetBlockEnvironment{quotation} % Sets the quotation environment to have no indentations

\\usepackage{geometry}
\\geometry{margin=1cm}
% [left=1.5in, right=1in, top=1.2in, bottom=1in]{geometry}
\\usepackage{graphicx}
%\\usepackage{enumitem}
%\\usepackage{amsmath, amssymb}
%\\usepackage{tcolorbox}

\\setlength{\\columnsep}{0.8cm}
%\\renewcommand{\\questionshook}{%
%\\setlength{\\leftmargin}{0pt}%
%\\setlength{\\labelwidth}{-\\labelsep}%
%\\setlength{\\parskip}{0.5em}
%\\setlength{\\parindent}{0pt}

% Remove indentation from quote environment
\\renewenvironment{quote}
  {\\list{}{\\leftmargin=0pt \\rightmargin=0pt}%
   \\item\\relax}
  {\\endlist}

% Custom command for author formatting
\\newcommand{\\quoteauthor}[1]{%
    \\begin{flushright}
        \\textit{\\small --- #1}
    \\end{flushright}
}

% tabularx column type
\\newcolumntype{L}{>{\\raggedright\\arraybackslash}X}

\\tolerance=1
\\emergencystretch=\maxdimen
\\hyphenpenalty=10000
\\hbadness=10000

% -------- allow \choice inside table cells (noparchoices) ----------
\\makeatletter
\\newenvironment{noparchoices}{%
  \\setcounter{choice}{0}%
  \\def\\choice{%
    \\refstepcounter{choice}%
    \\choicelabel
    \\questionobject@pluspagecheck
  }%
  \\def\\CorrectChoice{%
    \\refstepcounter{choice}%
    \\ifprintanswers
      \\begingroup\CorrectChoice@Emphasis
      \\choicelabel
      \\endgroup
    \\else
      \\choicelabel
    \\fi
    \\questionobject@pluspagecheck
  }%
  \\let\\correctchoice\\CorrectChoice
  \\ignorespaces
}{}
\\makeatother
% -------------------------------------------------------------------

% Format ONLY the question number: (1), (2)... in large bold
%\\qformat{\\textbf{\\large\\thequestion}\\quad}

% Put the question number on its own line; do NOT include any blank line or \par here.
\\qformat{%
  \\vspace{1.25\\baselineskip}% space before the number
  \\hspace*{\\parindent}\\bfseries\\LARGE\\thequestion.
  \\vspace{1\\baselineskip}% extra space after the number
}

% Make the question text align with the normal paragraph area (not in the margin).
\\renewcommand{\\questionshook}{%
  \\setlength{\\leftmargin}{0pt}%
  \\setlength{\\labelwidth}{-\labelsep}%
}

% Format choice labels as (A), (B), (C) ...
\\renewcommand{\\choicelabel}{(\\Alph{choice})}

% --- Make the answer key show only the letter (A), (B) ---
%\\renewcommand{\\answerkeyformat}[1]{#1}

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
    print(text_no_math)
    
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

    print(math_placeholders)
    
    # Restore the protected math content.
    for i, math_content in reversed(list(enumerate(math_placeholders))):
        placeholder = f"MATHPLACEHOLDER{i}"
        fully_escaped_text = fully_escaped_text.replace(placeholder, math_content)

    return fully_escaped_text
    
    
    

def markdown_to_latex2(md: str) -> str:
    """Convert Markdown-formatted text to LaTeX, with nested * / _ emphasis and math support."""

    print('######################################################################################')
    print('1', md)
    
    # --- Step 1: Temporarily protect math ($...$, $$...$$) ---
    math_blocks = {}

    def protect_math(match):
        key = f"__MATHBLOCK{len(math_blocks)}__"
        math_blocks[key] = match.group(0)
        return key

    protected = re.sub(r"\$\$.*?\$\$", protect_math, md, flags=re.DOTALL)
    protected = re.sub(r"\$[^$]+\$", protect_math, protected)

    tex = protected

    print('2', tex)
    
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
    
    print('3', tex)

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
    return "\\vspace{1.25\\baselineskip}\n\\textbf{" + markdown_to_latex(text) + "}\n\n"
    
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

    print('teste', list(p_el.itertext()))
    text = "".join(p_el.itertext()).strip()
    #print('0', text)
    #return markdown_to_latex(escape_latex(text)) + "\n\n"
    return markdown_to_latex(text) + "\n\n"

def render_inline_paragraph(p_el) -> str:
    text = "".join(p_el.itertext()).strip()
    return markdown_to_latex(text)

#########################################################################################################################
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
    parts.append("\\begin{quote}\n")
    
    inner_ps = q_el.findall("./p")
    if inner_ps:   
        for p in inner_ps:
            parts.append(render_paragraph(p))
        
    author_el = q_el.find("./author")
    if author_el is not None and (author_el.text or "").strip():
        author = strip_md_italics(author_el.text or "")
        #parts.append("\\begin{flushright}\\textit{" + escape_latex(author) + "}\\end{flushright}\n")
        parts.append("\\quoteauthor{" + escape_latex(author) + "}\n")
    
    parts.append("\\end{quote}\n")
    parts.append("\n")
    return "".join(parts)
    
def render_verse(q_el) -> str:
    parts = []
    parts.append("\\begin{verse}\n")
    
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
    
    parts.append("\\end{verse}\n")
    parts.append("\n")
    return "".join(parts)

def render_image(img_el, graphics_dir: Optional[Path]) -> str:
    src = img_el.get("src", "").strip()
    if graphics_dir:
        img_path = graphics_dir / src
    else:
        img_path = Path(src)
    # Use width=\linewidth to fit page
    return "\\begin{center}\n\\includegraphics[width=\\linewidth]{" + escape_latex(str(img_path).replace('\\','/')) + "}\n\\end{center}\n\n"

def count_table_cols(tr_el) -> int:
    return len(tr_el.findall("./cell")) # + len(tr_el.findall("./th"))

def render_table(tbl_el) -> str:
    headers =  tbl_el.findall("./header")
    rows = tbl_el.findall("./row")
    if not rows:
        return ""
    
    ncols = max((count_table_cols(r) for r in rows), default=1)
    # Simple table with vertical bars
    colspec = "|".join(["l"] * ncols)
    parts = []
    parts.append("\\begin{center}\n")
    parts.append("\\begin{tabular}{" + "|" + colspec + "|}\n\\hline\n")
    for r in headers:
        cells = []
        # preserve order of th/td as they appear
        for cell in list(r):
            #if cell.tag not in ("td", "th"):
            #    continue
            txt = "".join(cell.itertext()).strip()
            cells.append(markdown_to_latex(txt))
        parts.append(" & ".join(cells) + " \\\\ \\hline\n")
        
    for r in rows:
        cells = []
        # preserve order of th/td as they appear
        for cell in list(r):
            #if cell.tag not in ("td", "th"):
            #    continue
            txt = "".join(cell.itertext()).strip()
            cells.append(markdown_to_latex(txt))
        parts.append(" & ".join(cells) + " \\\\ \\hline\n")
    parts.append("\\end{tabular}\n")
    parts.append("\\end{center}\n\n")
    return "".join(parts)

def render_list(ul_el) -> str:
    parts = []
    parts.append("\\begin{itemize}\n")
    for li in ul_el.findall("./li"):
        txt = "".join(li.itertext()).strip()
        parts.append("\\item " + markdown_to_latex(txt) + "\n")
    parts.append("\\end{itemize}\n\n")
    return "".join(parts)

#########################################################################################################################
# Render the <context> tag

def render_context(ctx_el, graphics_dir: Optional[Path]) -> str:
    # Render as a boxed environment
    parts = []
    #parts.append("\\begin{tcolorbox}[colback=white,colframe=black!30]\n")
    # context may contain paragraphs and other elements
    for child in ctx_el:
        parts.append(render_statement_child(child, graphics_dir))
    #parts.append("\\end{tcolorbox}\n\n")
    return "".join(parts)
    
    

def render_statement_child(el, graphics_dir: Optional[Path]) -> str:
    tag = el.tag
    if tag == "p":
        return render_paragraph(el)
    if tag == "header":
        return render_header(el)
    if tag == "quote":
        return render_quote(el)
    if tag == "verse":
        return render_verse(el)
    if tag == "image":
        return render_image(el, graphics_dir)
    if tag == "table":
        return render_table(el)
    if tag == "ul":
        return render_list(el)
    #if tag == "context":
    #    return render_context(el, graphics_dir)
    # Fallback: render text
    return markdown_to_latex("".join(el.itertext()).strip()) + "\n\n"

#########################################################################################################################
# Render the <statement> tag

def render_statement(stmt_el, graphics_dir: Optional[Path]) -> str:
    parts = []
    for child in stmt_el:
        parts.append(render_statement_child(child, graphics_dir))
    return "".join(parts)


def count_table_cols2(tr_el) -> int:
    return len(tr_el.findall("./cell")) # + len(tr_el.findall("./th"))

#########################################################################################################################
# Render the <assumptions> tag

def render_assumptions(assumptions_el) -> str:
    # We will render as enumerate with labels (A), (B), ...
    parts = []
    
    parts.append("\\noindent\\fbox{\\begin{minipage}{\\textwidth}\n")
    parts.append("Note e adote:\n\n")
    for child in assumptions_el:
        parts.append(render_statement_child(child, global_graphics_dir))
    parts.append("\\end{minipage}}\n")
        
    return "".join(parts)
    
#########################################################################################################################
# Render the <quote> tag

def render_options(options_el) -> str:
    # We will render as enumerate with labels (A), (B), ...
    parts = []

    
    table_el = options_el.find("./table")
    print('teste', table_el)
    
    if table_el is not None:
        print('&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&')
        parts.append("\\begin{noparchoices}\n")
        parts.append("\\renewcommand{\\arraystretch}{1.25}\n")
        parts.append("\\begin{tabularx}{\\linewidth}{|c|L|L|}\n")
        parts.append("\\hline\n")
        print("$$", table_el)
        
        #for tbl in table_el:  
        headers = table_el.findall("./cell")
        header = table_el.find("./header")
        options = table_el.findall("./option")
        print('@', headers, type(headers))
        print('#', header, type(header))
        # for r in header:
            # print(r)
        #print('3', len(header.findall("./th")))
        
        #for opt in options
        ncols = max((count_table_cols(r) for r in options), default=1) + 1
        print('!', ncols)
        
        # output header
        if header is not None:
            for cell in header.findall("./cell"):
                print('col header', cell)
                parts.append(" & ")
                if cell.find("./p") is not None:
                    #text = "".join(cell.itertext()).strip()
                    #parts.append(markdown_to_latex(text))
                    parts.append(render_inline_paragraph(cell))
                    #print('0', text)
                    #return markdown_to_latex(escape_latex(text)) + "\n\n"
                    #return markdown_to_latex(text) + "\n\n"
                elif cell.find("./image") is not None:
                    img_el = cell.find("./image")
                    print('oi', img_el)
                    src = img_el.get("src", "").strip()
                    if global_graphics_dir:
                        img_path = global_graphics_dir / src
                    else:
                        img_path = Path(src)
                    # Use width=\linewidth to fit page

                else:
                    raise ValueError("XML contains unexpected 'invalid_tag' element.")
                
            parts.append("\\\\\n")
            parts.append("\\hline\n")
        
        # options
        
        for row in table_el.findall("./option"):
            parts.append("\\choice ")
            for cell in row.findall("./cell"):
                parts.append(" & ")
                print('cell', cell, table_el.find("./p"))
                if cell.find("./p") is not None:
                    parts.append(render_inline_paragraph(cell))
                elif cell.find("./image") is not None:
                    img_el = cell.find("./image")
                    print('oi', img_el)
                    src = img_el.get("src", "").strip()
                    if global_graphics_dir:
                        img_path = global_graphics_dir / src
                    else:
                        img_path = Path(src)
                    # Use width=\linewidth to fit page
                    parts.append("\\includegraphics[width=\\linewidth]{" + escape_latex(str(img_path).replace('\\','/')) + "}")
                    #return "\\begin{center}\n\\includegraphics[width=\\linewidth]{" + escape_latex(str(img_path).replace('\\','/')) + "}\n\\end{center}\n\n"

                else:
                    raise ValueError("XML contains unexpected 'invalid_tag' element.")
            
            parts.append("\\\\\n")
            parts.append("\\hline\n")
        
#         parts.append("""
# \\begin{noparchoices}
# \\renewcommand{\\arraystretch}{1.25}
# \\begin{tabularx}{\\linewidth}{|c|L|L|}
# \\hline
# \\textbf{Choice} & \\textbf{Formula} & \\textbf{Compound} \\\\
# \\hline
# \\choice        & CO$_2$ & Carbon dioxide \\\\
# \\hline
# \\choice        & O$_2$  & Oxygen \\\\
# \\hline
# \\choice        & H$_2$O & Water \\\\
# \\hline
# \\choice        & H$_2$  & Hydrogen gas \\\\
# \\hline
# \\end{tabularx}
# \\end{noparchoices}
# """)
            
            # rows = tbl_el.findall("./option")
            # if not rows:
                # return ""
            # ncols = max((count_table_cols(r) for r in rows), default=1)
            # # Simple table with vertical bars
            # colspec = "|".join(["l"] * ncols)
            # parts = []
            # parts.append("\\begin{center}\n")
            # parts.append("\\begin{tabular}{" + "|" + colspec + "|}\n\\hline\n")
            
            # for r in rows:
                # cells = []
                # # preserve order of th/td as they appear
                # for cell in list(r):
                    # if cell.tag not in ("td", "th"):
                        # continue
                    # txt = "".join(cell.itertext()).strip()
                    # cells.append(escape_latex(txt))
                # parts.append(" & ".join(cells) + " \\\\ \\hline\n")
            # parts.append("\\end{tabular}\n")
            # parts.append("\\end{center}\n\n")
            #return "".join(parts)
        
        ###############################
        parts.append("\\end{tabularx}\n")
        parts.append("\\end{noparchoices}\n\n")
    
    else:
        print('$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$')
        parts.append("\\begin{choices}\n")
        for opt in options_el.findall("./option"):
            label = opt.get("label")  # not strictly needed, enumerate will label
            # Option body can have paragraphs; concatenate them
            body_parts = []
            for child in opt:
                if child.tag == "p":
                    body_parts.append("".join(child.itertext()).strip())
                else:
                    body_parts.append("".join(child.itertext()).strip())
            body = markdown_to_latex("\n".join([t for t in body_parts if t])).strip()
            parts.append("\\choice " + body + "\n")
            
        parts.append("\\end{choices}\n\n")

    return "".join(parts)


#########################################################################################################################
#

def render_question(q_el, graphics_dir: Optional[Path], show_numbers: bool = True):

    # process the question number
    number = q_el.get("number", "").strip()
    #header = f"\\addtolength{\\itemsep}{1.25\\baselineskip}\\n"
    #header = "\\addtolength{\\itemsep}{0.50\\baselineskip}\n\\question\n" #if show_numbers else ""
    header = "\\question\n\\vspace{1.25\\baselineskip}% space before the number" #if show_numbers else ""
    
    #if number:
    #    header = f"\\question[\\textbf{{{escape_latex(number)}}}] "
    
    parts = [header + "\n"]
    
    # process the statement tag
    stmt = q_el.find("./statement")
    if stmt is not None:
        parts.append(render_statement(stmt, graphics_dir))
        
    # process the options tag
    options = q_el.find("./options")
    if options is not None:
        parts.append(render_options(options))
        
    assumptions = q_el.find("./assumptions")
    if assumptions is not None:
        parts.append(render_assumptions(assumptions))
    
    
    return "".join(parts)
    

def collect_answer(q_el) -> Optional[str]:
    ca = q_el.find("./correct_answer")
    if ca is None:
        return None
    txt = (ca.text or "").strip()
    if txt:
        num = q_el.get("number", "").strip()
        return f"{num}: {txt}"
    return None

#########################################################################################################################
#

def create_latex(doc: etree._ElementTree, graphics_dir: Optional[Path]) -> str:
    root = doc.getroot()
    name = root.get("name", "Exam")
    year = root.get("year", "")
    phase = root.get("phase", "")
    day = root.get("day", "")
    variation = root.get("variation", "")

    # Header
    preamble = [DEFAULT_PREAMBLE]
    
    title_line = f"{markdown_to_latex(name)} {markdown_to_latex(year)}"
    subtitle = " ".join(filter(None, [markdown_to_latex(phase), markdown_to_latex(day), markdown_to_latex(variation)]))
    title_full = title_line + (f" --- {subtitle}" if subtitle else "")
    
    preamble.append("\\title{" + title_full + "}\n")
    preamble.append("\\date{}\n")
    preamble.append("\\author{}\n")
    preamble.append("\n")
    preamble.append("\\begin{document}\n\\maketitle\n\\begin{multicols}{2}\n\\begin{questions}\n\n")
    #else:
    #    preamble.append("\\begin{document}\n")
    #    preamble.append("\\section*{" + escape_latex(name) + " " + escape_latex(year) + "}\n")

    
    body = []

    answers: List[str] = []

    # Context blocks can appear as siblings to question_group, handle flexibly
    for child in root:
        #print(child)
        
        if child.tag == "subject":
            raise NotImplementedError("Subject tag")
            
        elif child.tag == "question_group":
        
            print(child)
            # Each group can have optional <context> followed by questions
            context = child.find("./context")
            if context is not None:
                body.append(render_context(context, graphics_dir))
                
            for q in child.findall("./question"):
                body.append(render_question(q, graphics_dir))
                ans = collect_answer(q)
                if ans:
                    answers.append(ans)
                    
        # if child.tag == "context":
            # body.append(render_context(child, graphics_dir))
        # elif child.tag == "question_group":
            # # Each group can have optional <context> followed by questions
            # ctx = child.find("./context")
            # if ctx is not None:
                # body.append(render_context(ctx, graphics_dir))
            # for q in child.findall("./question"):
                # body.append(render_question(q, graphics_dir))
                # ans = collect_answer(q)
                # if ans:
                    # answers.append(ans)
                    
    #print(preamble)
    #print(body)

    ending = []
    
   
    # if answers:
        # if docclass == "exam":
            # ending.append("\\newpage\n\\section*{Gabarito}\n")
        # else:
            # ending.append("\\newpage\n\\section*{Answer Key}\n")
        # ending.append("\\begin{itemize}\n")
        # for a in answers:
            # ending.append("\\item " + escape_latex(a) + "\n")
        # ending.append("\\end{itemize}\n")

    #if docclass == "exam":
    ending.append("\\end{questions}\n\\end{multicols}\n\\end{document}\n")
    #else:
    #    ending.append("\\end{document}\n")

    return "".join(preamble + body + ending)
    
def read_parser_arguments():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path, help="Input exam XML file")
    #ap.add_argument("xsd", type=Path, help="XSD schema file")
    ap.add_argument("out", type=Path, help="Output .tex file path")
    ap.add_argument("--graphics-dir", type=Path, default=None, help="Base directory to prefix image src paths (optional)")
    #ap.add_argument("--docclass", type=str, default="exam", help="LaTeX document class to use (exam|article). Default: exam")
    
    return ap.parse_args()

def main():

    # Declare intent to modify the global variable
    global global_graphics_dir

    args = read_parser_arguments()
    
    global_graphics_dir = args.graphics_dir

    xml_input = read_xml(args.xml)
    #validate_xml(doc, args.xsd)
    validate_xml(xml_input, ".\\xsd\\fuvest_xml.xsd")

    tex = create_latex(xml_input, args.graphics_dir)
    #print(tex)
    #print(type(args.out))
    
    with open(args.out, 'w', encoding='utf-8') as file:
    # Write the variable's content to the file
        file.write(tex)
    
    #args.out.write_text(tex, encoding="utf-8")
    print(f"Wrote LaTeX to {args.out}")

if __name__ == "__main__":
    main()
