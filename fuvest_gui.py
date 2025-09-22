import os
import glob
import sys
import pandas as pd
from lxml import etree
import re

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableView, QHeaderView, QVBoxLayout,
    QWidget, QMenu, QAction, QSplitter, QLineEdit, QTabWidget,
    QPlainTextEdit, QTextBrowser, QHBoxLayout, QPushButton, QStatusBar
)
from PyQt5.QtCore import Qt, QRect, QSortFilterProxyModel
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QPainter, QPainterPath, QColor

from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import QRegExp

from PyQt5.QtWidgets import QHeaderView

import re
from PyQt5.QtCore import QSortFilterProxyModel

class ExprNode:
    """Boolean expression tree node"""
    def __init__(self, kind, value=None, left=None, right=None):
        self.kind = kind    # "term", "and", "or"
        self.value = value  # criterion (for term)
        self.left = left
        self.right = right

    def evaluate(self, row_vals, match_func):
        if self.kind == "term":
            return match_func(self.value, *row_vals)
        elif self.kind == "and":
            return self.left.evaluate(row_vals, match_func) and self.right.evaluate(row_vals, match_func)
        elif self.kind == "or":
            return self.left.evaluate(row_vals, match_func) or self.right.evaluate(row_vals, match_func)
        return False


class MultiColumnFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.filters = {}      # funnel filters
        self.expr_root = None  # parsed search expression tree

    def set_filter_values(self, column, values):
        self.filters[column] = {str(v).strip() for v in values}
        self.invalidateFilter()

    def clear_all_filters(self):
        self.filters.clear()
        self.expr_root = None
        self.invalidateFilter()

    def set_text_filter(self, text: str):
        """Parse text into boolean expression tree"""
        self.expr_root = self._parse_expression(text)
        self.invalidateFilter()

    # ------------------- Expression Parser -------------------
    def _tokenize(self, text):
        # tokens: words, and, or, (, )
        tokens = re.findall(r'\(|\)|\w+|\&|\|', text.lower())
        return ["and" if t in ["and", "&"] else "or" if t in ["or", "|"] else t for t in tokens]

    def _parse_expression(self, text):
        tokens = self._tokenize(text)
        if not tokens:
            return None

        # Shunting-yard to RPN
        prec = {"or": 1, "and": 2}
        output, stack = [], []
        for tok in tokens:
            if tok not in ("and", "or", "(", ")"):
                output.append(tok)
            elif tok in ("and", "or"):
                while stack and stack[-1] in prec and prec[stack[-1]] >= prec[tok]:
                    output.append(stack.pop())
                stack.append(tok)
            elif tok == "(":
                stack.append(tok)
            elif tok == ")":
                while stack and stack[-1] != "(":
                    output.append(stack.pop())
                if stack and stack[-1] == "(":
                    stack.pop()
        while stack:
            if stack[-1] in ("(", ")"):  # skip unmatched parens
                stack.pop()
            else:
                output.append(stack.pop())

        # Build expression tree from RPN
        stack = []
        for tok in output:
            if tok not in ("and", "or"):
                stack.append(ExprNode("term", tok))
            else:
                # Need at least two operands
                if len(stack) < 2:
                    continue  # skip invalid operator
                right = stack.pop()
                left = stack.pop()
                stack.append(ExprNode(tok, left=left, right=right))

        return stack[0] if stack else None


    # ------------------- Filtering Logic -------------------
    def filterAcceptsRow(self, source_row, parent):
        sm = self.sourceModel()

        # Apply funnel filters first
        for col, allowed in self.filters.items():
            idx = sm.index(source_row, col, parent)
            if not idx.isValid():
                continue
            cell = str(idx.data()).strip()
            if cell not in allowed:
                return False

        # Apply search expression if exists
        if self.expr_root:
            col_map = {self.sourceModel().headerData(i, Qt.Horizontal): i
                for i in range(self.sourceModel().columnCount())}

            def safe_get(colname):
                ci = col_map.get(colname)
                return str(sm.index(source_row, ci, parent).data()).lower() if ci is not None else ""

            year_val = safe_get("year")
            exam_val = safe_get("exam_name")
            subj_val = safe_get("classification")
            row_text = f"{year_val} {exam_val} {subj_val}"

            return self.expr_root.evaluate(
                (year_val, exam_val, subj_val, row_text),
                self._match_criterion
            )

        return True

    def _match_criterion(self, crit, year_val, exam_val, subj_val, row_text):
        if crit.isdigit():
            return crit == year_val
        elif crit in ["fuvest", "enem", "unicamp", "ita"]:
            return crit in exam_val
        elif crit in ["math", "biology", "history", "geography"]:
            return subj_val.startswith(crit)
        else:
            return crit in row_text



class XMLHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Tag names (<tag>, </tag>)
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor("blue"))
        tag_format.setFontWeight(QFont.Bold)
        self.tag_pattern = QRegExp("</?\\b[^>]+>")
        self.tag_format = tag_format

        # Attribute names
        attr_format = QTextCharFormat()
        attr_format.setForeground(QColor("red"))
        self.attr_pattern = QRegExp("\\b\\w+(?=\\=)")
        self.attr_format = attr_format

        # Attribute values in quotes
        val_format = QTextCharFormat()
        val_format.setForeground(QColor("darkgreen"))
        self.val_pattern = QRegExp("\".*\"")
        self.val_format = val_format

        # Comments <!-- ... -->
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("gray"))
        self.comment_pattern = QRegExp("<!--[^>]*-->")
        self.comment_format = comment_format

    def highlightBlock(self, text):
        # Tags
        i = self.tag_pattern.indexIn(text)
        while i >= 0:
            length = self.tag_pattern.matchedLength()
            self.setFormat(i, length, self.tag_format)
            i = self.tag_pattern.indexIn(text, i + length)

        # Attributes
        i = self.attr_pattern.indexIn(text)
        while i >= 0:
            length = self.attr_pattern.matchedLength()
            self.setFormat(i, length, self.attr_format)
            i = self.attr_pattern.indexIn(text, i + length)

        # Attribute values
        i = self.val_pattern.indexIn(text)
        while i >= 0:
            length = self.val_pattern.matchedLength()
            self.setFormat(i, length, self.val_format)
            i = self.val_pattern.indexIn(text, i + length)

        # Comments
        i = self.comment_pattern.indexIn(text)
        while i >= 0:
            length = self.comment_pattern.matchedLength()
            self.setFormat(i, length, self.comment_format)
            i = self.comment_pattern.indexIn(text, i + length)



import os
import glob
import pandas as pd
from lxml import etree

def find_question_element(source_file: str, qtype: str, qnumber: str):
    """
    Return the first <objective_question> or <discursive_question> element
    matching @id == qnumber OR @number == qnumber. Uses full XPath.
    """
    if not source_file or not qtype:
        return None

    # Be lenient with parser so a bad file doesn't crash the UI
    parser = etree.XMLParser(recover=True)
    try:
        tree = etree.parse(source_file, parser)
    except Exception as e:
        print(f"[find_question_element] Failed to parse {source_file}: {e}")
        return None

    # Full XPath with variable binding (avoids manual quoting issues)
    qn = "" if qnumber is None else str(qnumber)
    try:
        nodes = tree.xpath(f".//{qtype}[@id=$n or @number=$n]", n=qn)
        if nodes:
            return nodes[0]
        # Fallbacks (some files may use only one of the attributes)
        nodes = tree.xpath(f".//{qtype}[@id=$n]", n=qn)
        if nodes:
            return nodes[0]
        nodes = tree.xpath(f".//{qtype}[@number=$n]", n=qn)
        if nodes:
            return nodes[0]
    except Exception as e:
        print(f"[find_question_element] XPath error in {source_file}: {e}")
    return None



def get_dataframe():
    schema_path = "./xsd/fuvest_xml.xsd"
    exams_dir = "./exams"

    # Load XML Schema
    with open(schema_path, "rb") as f:
        schema_root = etree.XML(f.read())
    schema = etree.XMLSchema(schema_root)
    parser = etree.XMLParser(schema=schema)

    rows = []

    for xml_file in glob.glob(os.path.join(exams_dir, "*.xml")):
        try:
            tree = etree.parse(xml_file, parser)
        except etree.XMLSyntaxError as e:
            print(f"Schema validation failed for {xml_file}: {e}")
            continue

        root = tree.getroot()
        exam_name = root.get("name")
        exam_year = root.get("year")
        exam_phase = root.get("phase")

        for qtag in ["objective_question", "discursive_question"]:
            for q in root.findall(f".//{qtag}"):
                q_number = q.get("id") or q.get("number")
                classification = None
                cl = q.find(".//classification")
                if cl is not None and cl.get("subject"):
                    classification = cl.get("subject")
                text = (q.text or "").strip()

                rows.append({
                    "exam_name": exam_name,
                    "year": exam_year,
                    "phase": exam_phase,
                    "question_type": qtag,
                    "question_number": q_number,
                    "classification": classification,
                    #"question_text": text,
                    "source_file": xml_file  # store file path!
                })

    return pd.DataFrame(rows)


def xml_to_html(elem):
    """
    Convert a <objective_question> or <discursive_question> XML element
    into an HTML string, with Markdown/MathJax formatting.
    """
    parts = []

    def recurse(node):
        if node.text:
            parts.append(node.text)

        for child in node:
            tag = child.tag.lower()
            if tag in ("b", "strong"):
                parts.append(f"<b>{child.text or ''}</b>")
            elif tag in ("i", "em"):
                parts.append(f"<i>{child.text or ''}</i>")
            elif tag == "classification":
                subj = child.get("subject", "")
                parts.append(f"<p><b>Subject:</b> {subj}</p>")
            elif tag == "choice":
                parts.append(f"<li>{child.text or ''}</li>")
            elif tag == "math":
                # Wrap in MathJax delimiters
                math_content = (child.text or "").strip()
                # Inline if short, block if long
                if len(math_content) < 50 and "\n" not in math_content:
                    parts.append(f"\\({math_content}\\)")
                else:
                    parts.append(f"\\[{math_content}\\]")
            else:
                recurse(child)

            if child.tail:
                parts.append(child.tail)

    recurse(elem)
    html = "".join(parts)

    if elem.tag == "objective_question":
        html = f"<p><b>Objective Question {elem.get('id') or elem.get('number')}</b></p><ul>{html}</ul>"
    elif elem.tag == "discursive_question":
        html = f"<p><b>Discursive Question {elem.get('id') or elem.get('number')}</b></p><p>{html}</p>"

    # Add MathJax loader script for rendering
    html += """
    <script type="text/javascript"
      id="MathJax-script"
      async
      src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
    </script>
    """

    return html



# ---------------- DATA MODEL ----------------
class DataFrameModel(QStandardItemModel):
    def __init__(self, df):
        super().__init__()
        self.setColumnCount(len(df.columns))
        self.setRowCount(len(df.index))
        self.setHorizontalHeaderLabels(df.columns.tolist())
        for r in range(len(df.index)):
            for c, v in enumerate(df.iloc[r, :]):
                self.setItem(r, c, QStandardItem(str(v)))


# ---------------- FILTER HEADER ----------------
class FilterHeader(QHeaderView):
    ICON_SIZE = 14

    def __init__(self, df, proxy, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.proxy = proxy
        self.setSectionsClickable(True)

        self.unique_vals = {i: [str(x) for x in sorted(set(df.iloc[:, i].astype(str)))]
                            for i in range(df.shape[1])}
        self.selected_vals = {i: set(self.unique_vals[i]) for i in range(df.shape[1])}

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        painter.fillRect(rect, QColor(240, 240, 240))
        text = str(self.model().headerData(logicalIndex, Qt.Horizontal, Qt.DisplayRole))
        painter.drawText(rect.adjusted(6, 0, -20, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

        icon_rect = QRect(rect.right() - self.ICON_SIZE - 4,
                          rect.center().y() - self.ICON_SIZE // 2,
                          self.ICON_SIZE, self.ICON_SIZE)

        all_selected = len(self.selected_vals[logicalIndex]) == len(self.unique_vals[logicalIndex])
        path = QPainterPath()
        if all_selected:
            cx, cy = icon_rect.center().x(), icon_rect.center().y()
            path.moveTo(cx - 5, cy - 3)
            path.lineTo(cx + 5, cy - 3)
            path.lineTo(cx, cy + 4)
            path.closeSubpath()
        else:
            x, y, w, h = icon_rect.x(), icon_rect.y(), icon_rect.width(), icon_rect.height()
            path.moveTo(x, y)
            path.lineTo(x + w, y)
            path.lineTo(x + w/2 + 3, y + h/2)
            path.lineTo(x + w/2 + 3, y + h)
            path.lineTo(x + w/2 - 3, y + h)
            path.lineTo(x + w/2 - 3, y + h/2)
            path.closeSubpath()

        painter.fillPath(path, Qt.black)
        painter.restore()

    def mousePressEvent(self, event):
        for col in range(self.model().columnCount()):
            icon_rect = QRect(
                self.sectionViewportPosition(col) + self.sectionSize(col) - self.ICON_SIZE - 4,
                (self.height() - self.ICON_SIZE) // 2,
                self.ICON_SIZE, self.ICON_SIZE
            )
            if icon_rect.contains(event.pos()):
                self._show_filter_menu(col, event.globalPos())
                return
        super().mousePressEvent(event)

    def _show_filter_menu(self, col, global_pos):
        uniq = self.unique_vals[col]
        curr = self.selected_vals[col]

        menu = QMenu(self)
        all_action = QAction("All", self, checkable=True)
        all_action.setChecked(len(curr) == len(uniq))
        menu.addAction(all_action)
        menu.addSeparator()

        actions = []
        for val in uniq:
            a = QAction(val, self, checkable=True)
            a.setChecked(val in curr)
            menu.addAction(a)
            actions.append(a)

        def apply():
            sender = menu.sender()
            selected = {a.text() for a in actions if a.isChecked()}

            if sender is all_action:
                if all_action.isChecked():
                    selected = set(uniq)
                    for a in actions:
                        a.blockSignals(True); a.setChecked(True); a.blockSignals(False)
                else:
                    selected = set()
                    for a in actions:
                        a.blockSignals(True); a.setChecked(False); a.blockSignals(False)
            else:
                all_action.blockSignals(True)
                all_action.setChecked(len(selected) == len(uniq))
                all_action.blockSignals(False)

            self.selected_vals[col] = selected
            self.proxy.set_filter_values(col, selected)
            self.viewport().update()

        all_action.toggled.connect(apply)
        for a in actions:
            a.toggled.connect(apply)

        menu.exec_(global_pos)


# ---------------- MAIN WINDOW ----------------
class MainWindow(QMainWindow):
    def __init__(self, df):
        super().__init__()
        self.setWindowTitle("Filterable Table + HTML Viewer")

        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # LEFT: table + global search
        left = QWidget()
        left_layout = QVBoxLayout(left)

        ctrl_layout = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to filter (all columns)...")
        self.search.textChanged.connect(self.on_search_changed)

        clear_btn = QPushButton("Clear All Filters")
        ctrl_layout.addWidget(self.search)
        ctrl_layout.addWidget(clear_btn)
        left_layout.addLayout(ctrl_layout)

        self.model = DataFrameModel(df)
        self.proxy = MultiColumnFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.header = FilterHeader(df, self.proxy, self.table)
        self.table.setHorizontalHeader(self.header)

        left_layout.addWidget(self.table)
        splitter.addWidget(left)

        # RIGHT: HTML tabs
        tabs = QTabWidget()
        #self.html_code = QPlainTextEdit()
        #self.html_code.setReadOnly(True)

        self.html_code = QPlainTextEdit()
        self.html_code.setReadOnly(True)
        self.html_code.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Attach syntax highlighter
        self.highlighter = XMLHighlighter(self.html_code.document())
        tabs.addTab(self.html_code, "HTML Code")


        self.html_view = QTextBrowser()
        tabs.addTab(self.html_view, "Rendered")
        tabs.setCurrentIndex(1)
        splitter.addWidget(tabs)
        splitter.setSizes([700, 550])

        # STATUS BAR
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.update_status()

                # connections
        self.search.textChanged.connect(self.on_search_changed)
        self.table.clicked.connect(self.row_clicked)

        def clear_all():
            header.proxy.clear_all_filters()
            header.viewport().update()
            self.search.clear()
            self.update_status()
        clear_btn.clicked.connect(clear_all)

        # Also update status whenever proxy changes
        self.proxy.rowsInserted.connect(lambda *_: self.update_status())
        self.proxy.rowsRemoved.connect(lambda *_: self.update_status())
        self.proxy.modelReset.connect(lambda *_: self.update_status())
        self.proxy.layoutChanged.connect(lambda *_: self.update_status())

        # Auto resize columns dynamically
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeToContents)
        header_view.setStretchLastSection(True)

        # Start fullscreen
        self.showMaximized()


    # def on_search_changed(self, text):
    #     self.proxy.setFilterFixedString(text)
    #     self.update_status()

    def on_search_changed(self, text):
        self.proxy.set_text_filter(text)
        self.update_status()



    def update_status(self, *args):
        shown = self.proxy.rowCount()
        total = self.model.rowCount()
        self.status.showMessage(f"{shown} of {total} rows shown")


    def row_clicked(self, index):
        # Map from proxy to source row
        src = self.proxy.mapToSource(index)
        r = src.row()

        # Build a header->column index map so we don't rely on hard-coded positions
        header_map = {self.model.headerData(i, Qt.Horizontal): i
                    for i in range(self.model.columnCount())}

        def cell(col_name, default=""):
            ci = header_map.get(col_name)
            return self.model.item(r, ci).text() if ci is not None and self.model.item(r, ci) else default

        # Expected columns from your get_dataframe(): adjust names if yours differ
        source_file = cell("source_file")
        qtype       = cell("question_type")
        qnumber     = cell("question_number")

        # Locate the exact question element using full XPath
        elem = find_question_element(source_file, qtype, qnumber)

        # Original XML (pretty) for the Code tab
        if elem is not None:
            xml_pretty = etree.tostring(elem, pretty_print=True, encoding="unicode")
        else:
            xml_pretty = "Question not found."

        # Show pretty XML in Code tab
        self.html_code.setPlainText(xml_pretty)
        self.html_code.setLineWrapMode(QPlainTextEdit.NoWrap)   # avoid wrapped lines
        self.html_code.setTabStopDistance(4 * self.html_code.fontMetrics().horizontalAdvance(' '))  # 4 spaces for tabs


        # Rendered HTML for the preview tab
        html_rendered = xml_to_html(elem)
        self.html_view.setHtml(html_rendered)




def main():
    app = QApplication(sys.argv)
    df = get_dataframe()
    w = MainWindow(df)
    w.resize(1250, 650)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
