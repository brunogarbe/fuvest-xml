import os
import sys
import glob
import re
import time
import pandas as pd
from lxml import etree


from pathlib import Path
from . import convert as fuvestxml

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTableView,
    QHeaderView,
    QVBoxLayout,
    QWidget,
    QMenu,
    QAction,
    QSplitter,
    QLineEdit,
    QTabWidget,
    QPlainTextEdit,
    QTextBrowser,
    QHBoxLayout,
    QPushButton,
    QStatusBar,
    QFileDialog,
    QMessageBox,
    QStyleOptionButton,
    QStyle,
)
from PyQt5.QtCore import Qt, QRect, QSortFilterProxyModel, QRegExp, QVariant
from PyQt5.QtGui import (
    QStandardItemModel,
    QStandardItem,
    QPainterPath,
    QColor,
    QSyntaxHighlighter,
    QTextCharFormat,
    QFont,
)

# from PyQt5.QtWidgets import QStyleOptionButton, QStyle


# -------------------------------------------------------------------
# Boolean expression tree (used in global search with AND/OR support)
# -------------------------------------------------------------------
class ExprNode:
    """Boolean expression tree node"""

    def __init__(self, kind, value=None, left=None, right=None):
        self.kind = kind  # "term", "and", "or"
        self.value = value  # criterion (for term)
        self.left = left
        self.right = right

    def evaluate(self, row_vals, match_func):
        if self.kind == "term":
            return match_func(self.value, *row_vals)
        elif self.kind == "and":
            return self.left.evaluate(row_vals, match_func) and self.right.evaluate(
                row_vals, match_func
            )
        elif self.kind == "or":
            return self.left.evaluate(row_vals, match_func) or self.right.evaluate(
                row_vals, match_func
            )
        return False


# -------------------------------------------------------------------
# Proxy model: filtering, sorting, alignment rules
# -------------------------------------------------------------------
class MultiColumnFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.filters = {}  # funnel filters
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
        print(text, self.expr_root)
        self.invalidateFilter()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        # Get header name for the current column
        header = self.sourceModel().headerData(index.column(), Qt.Horizontal)

        # Center specific columns
        if role == Qt.TextAlignmentRole and header in (
            "Select",
            "year",
            "question_number",
        ):
            return Qt.AlignCenter

        return super().data(index, role)

    # ------------------- Expression Parser -------------------
    def _tokenize(self, text):
        # tokens: words, and, or, (, )
        tokens = re.findall(r"\(|\)|\w+|\&|\|", text.lower())
        return [
            "and" if t in ["and", "&"] else "or" if t in ["or", "|"] else t
            for t in tokens
        ]

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
            col_map = {
                self.sourceModel().headerData(i, Qt.Horizontal): i
                for i in range(1, self.sourceModel().columnCount())
            }

            def safe_get(colname):
                ci = col_map.get(colname)
                return (
                    str(sm.index(source_row, ci, parent).data()).lower()
                    if ci is not None
                    else ""
                )

            year_val = safe_get("year")
            exam_val = safe_get("exam_name")
            subj_val = safe_get("classification")
            row_text = f"{year_val} {exam_val} {subj_val}"

            return self.expr_root.evaluate(
                (year_val, exam_val, subj_val, row_text), self._match_criterion
            )

        return True

    def _match_criterion(self, crit, year_val, exam_val, subj_val, row_text):
        if crit.isdigit():
            return crit == year_val
        elif crit in ["fuvest", "enem", "unicamp", "ita"]:
            return crit in exam_val
        else:  # crit in ["math:algebra", "math", "biology", "history", "geography"]:
            # print('################################################################')
            # print('subj_val', subj_val, type(subj_val), subj_val.startswith(crit), crit)
            return subj_val.startswith(crit)
        # else:
        #    return crit in row_text


# -------------------------------------------------------------------
# Syntax highlighter for XML view
# -------------------------------------------------------------------
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
        self.val_pattern = QRegExp('".*"')
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
    xml_files = glob.glob(os.path.join(exams_dir, "*.xml"))
    total = len(xml_files)

    start_time = time.time()

    for i, xml_file in enumerate(xml_files, start=1):
        print(f"[INFO] ({i}/{total}) Processing file: {xml_file}")

        try:
            tree = etree.parse(xml_file, parser)  # strict with schema
        except etree.XMLSyntaxError as e:
            print(f"[WARN] Schema validation failed for {xml_file}: {e}")
            # fallback without schema
            tree = etree.parse(xml_file, etree.XMLParser(recover=True))

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
                text = (q.text or "").strip() if q.text else ""

                rows.append(
                    {
                        "exam_name": exam_name,
                        "year": exam_year,
                        "phase": exam_phase,
                        "question_type": qtag,
                        "question_number": q_number,
                        "classification": classification,
                        "question_text": text,
                        "source_file": xml_file,
                    }
                )

    elapsed = time.time() - start_time
    print(f"[INFO] Finished processing {total} files in {elapsed:.2f} seconds.")
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


# -------------------------------------------------------------------
# Data model: Pandas DataFrame → QStandardItemModel
# -------------------------------------------------------------------
class DataFrameModel(QStandardItemModel):
    def __init__(self, df):
        super().__init__()
        self._df = df.copy()
        self._df.insert(0, "Selected", False)  # checkbox column
        self.setRowCount(len(self._df))
        self.setColumnCount(len(self._df.columns))
        self.setHorizontalHeaderLabels(self._df.columns)

        for r in range(len(self._df)):
            for c in range(len(self._df.columns)):
                val = self._df.iat[r, c]
                item = self.item(r, c)
                if item is None:
                    item = QStandardItem()
                    self.setItem(r, c, item)

                if self._df.columns[c] == "Selected":
                    item.setCheckable(True)
                    item.setCheckState(Qt.Unchecked if not val else Qt.Checked)
                else:
                    item.setText(str(val))

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        if self._df.columns[index.column()] == "Selected":
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
        return super().flags(index)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if self._df.columns[index.column()] == "Selected":
            if role == Qt.CheckStateRole:
                return (
                    Qt.Checked
                    if self._df.iat[index.row(), index.column()]
                    else Qt.Unchecked
                )
            return QVariant()
        return super().data(index, role)

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        if self._df.columns[index.column()] == "Selected":
            if role == Qt.CheckStateRole:
                self._df.iat[index.row(), index.column()] = value == Qt.Checked
                self.dataChanged.emit(index, index, [Qt.CheckStateRole])
                return True
        return super().setData(index, value, role)

    def get_selected_rows(self):
        """Return the DataFrame of selected rows (excluding the 'Selected' col)."""
        df = self._df[self._df["Selected"] == True].drop(columns=["Selected"])
        return df


# ---------------- FILTER HEADER ----------------
class FilterHeader(QHeaderView):
    ICON_SIZE = 14

    def __init__(self, table_view, proxy, parent=None):
        super().__init__(Qt.Horizontal, parent or table_view)
        self.table_view = table_view  # QTableView (to check hidden columns if needed)
        self.proxy = proxy  # QSortFilterProxyModel
        self.setSectionsClickable(True)

        # Columns that must NOT have funnels
        self.excluded_names = {"Selected", "question_text", "source_file"}

        # Maps keyed by *column index* (aligned with model/proxy)
        self.unique_vals = {}  # col_idx -> set(str)
        self.selected_vals = {}  # col_idx -> set(str)

        self.rebuild()  # build maps from the *source* model

    def rebuild(self):
        """Recompute unique/selected sets per real column from the source model."""
        self.unique_vals.clear()
        self.selected_vals.clear()

        src = self.proxy.sourceModel()
        if src is None:
            return

        col_count = src.columnCount()
        for col in range(col_count):
            name = src.headerData(col, Qt.Horizontal)
            # Skip non-filterable columns by name
            if str(name) in self.excluded_names:
                continue

            # Collect unique values from the *source* (unfiltered) data
            vals = set()
            for r in range(src.rowCount()):
                vals.add(str(src.index(r, col).data()).strip())

            self.unique_vals[col] = vals
            self.selected_vals[col] = set(vals)

        self.viewport().update()

    # ---------- painting ----------
    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        title = str(self.model().headerData(logicalIndex, Qt.Horizontal))

        painter.fillRect(rect, QColor(240, 240, 240))
        painter.drawText(
            rect.adjusted(6, 0, -20, 0), Qt.AlignVCenter | Qt.AlignLeft, title
        )

        # Special: draw a checkbox in the Selected column header
        if title == "Selected":
            style = self.style()
            opt = QStyleOptionButton()

            # Determine state from filtered rows
            proxy = self.parent().model()
            src_model = proxy.sourceModel()
            total = proxy.rowCount()
            checked = sum(
                1
                for r in range(total)
                if src_model.data(
                    proxy.mapToSource(proxy.index(r, logicalIndex)), Qt.CheckStateRole
                )
                == Qt.Checked
            )

            if checked == 0:
                opt.state = QStyle.State_Off | QStyle.State_Enabled
            elif checked == total:
                opt.state = QStyle.State_On | QStyle.State_Enabled
            else:
                opt.state = (
                    QStyle.State_NoChange | QStyle.State_Enabled
                )  # partially checked

            opt.rect = QRect(
                rect.right() - self.ICON_SIZE * 2,
                rect.center().y() - self.ICON_SIZE // 2,
                self.ICON_SIZE,
                self.ICON_SIZE,
            )
            style.drawControl(QStyle.CE_CheckBox, opt, painter)

            painter.restore()
            return

        # --- Normal filterable columns ---
        if logicalIndex not in self.unique_vals:
            painter.restore()
            return

        # (funnel drawing code as before…)
        # ...

        # # Only draw a funnel/arrow for filterable columns
        # if logicalIndex not in self.unique_vals:
        #     painter.restore()
        #     return

        icon_rect = QRect(
            rect.right() - self.ICON_SIZE - 4,
            rect.center().y() - self.ICON_SIZE // 2,
            self.ICON_SIZE,
            self.ICON_SIZE,
        )

        all_selected = (
            self.selected_vals[logicalIndex] == self.unique_vals[logicalIndex]
        )
        path = QPainterPath()
        if all_selected:
            # ▼
            cx, cy = icon_rect.center().x(), icon_rect.center().y()
            path.moveTo(cx - 5, cy - 3)
            path.lineTo(cx + 5, cy - 3)
            path.lineTo(cx, cy + 4)
            path.closeSubpath()
        else:
            # Funnel
            x, y, w, h = (
                icon_rect.x(),
                icon_rect.y(),
                icon_rect.width(),
                icon_rect.height(),
            )
            path.moveTo(x, y)
            path.lineTo(x + w, y)
            path.lineTo(x + w / 2 + 3, y + h / 2)
            path.lineTo(x + w / 2 + 3, y + h)
            path.lineTo(x + w / 2 - 3, y + h)
            path.lineTo(x + w / 2 - 3, y + h / 2)
            path.closeSubpath()

        painter.fillPath(path, Qt.black)
        painter.restore()

    # ---------- interaction ----------
    def mousePressEvent(self, event):
        logicalIndex = self.logicalIndexAt(event.pos().x())
        if logicalIndex < 0:
            super().mousePressEvent(event)
            return

        header_text = str(self.model().headerData(logicalIndex, Qt.Horizontal))

        if header_text == "Selected":
            # Compute rect of this header cell
            x = self.sectionViewportPosition(logicalIndex)
            w = self.sectionSize(logicalIndex)
            h = self.height()
            rect = QRect(x, 0, w, h)

            # Rect for checkbox
            checkbox_rect = QRect(
                rect.right() - self.ICON_SIZE * 2,
                rect.center().y() - self.ICON_SIZE // 2,
                self.ICON_SIZE,
                self.ICON_SIZE,
            )

            proxy = self.parent().model()
            src_model = proxy.sourceModel()

            if event.button() == Qt.LeftButton:
                # --- Left click: only toggle checkbox ---
                if checkbox_rect.contains(event.pos()):
                    total = proxy.rowCount()
                    checked = sum(
                        1
                        for r in range(total)
                        if src_model.data(
                            proxy.mapToSource(proxy.index(r, logicalIndex)),
                            Qt.CheckStateRole,
                        )
                        == Qt.Checked
                    )
                    if checked == total:
                        # all selected → deselect all
                        for r in range(total):
                            src_index = proxy.mapToSource(proxy.index(r, logicalIndex))
                            src_model.setData(
                                src_index, Qt.Unchecked, Qt.CheckStateRole
                            )
                    else:
                        # none/partial → select all
                        for r in range(total):
                            src_index = proxy.mapToSource(proxy.index(r, logicalIndex))
                            src_model.setData(src_index, Qt.Checked, Qt.CheckStateRole)
                    self.viewport().update()
                return

            elif event.button() == Qt.RightButton:
                # --- Right click: show menu ---
                menu = QMenu(self)
                select_all_action = QAction("Select All (filtered)", self)
                deselect_all_action = QAction("Deselect All (filtered)", self)
                invert_action = QAction("Invert Selection (filtered)", self)
                menu.addAction(select_all_action)
                menu.addAction(deselect_all_action)
                menu.addAction(invert_action)

                def apply_selection(mode):
                    for r in range(proxy.rowCount()):
                        src_index = proxy.mapToSource(proxy.index(r, logicalIndex))
                        current = src_model.data(src_index, Qt.CheckStateRole)
                        if mode == "select":
                            src_model.setData(src_index, Qt.Checked, Qt.CheckStateRole)
                        elif mode == "deselect":
                            src_model.setData(
                                src_index, Qt.Unchecked, Qt.CheckStateRole
                            )
                        elif mode == "invert":
                            new_state = (
                                Qt.Unchecked if current == Qt.Checked else Qt.Checked
                            )
                            src_model.setData(src_index, new_state, Qt.CheckStateRole)
                    self.viewport().update()

                select_all_action.triggered.connect(lambda: apply_selection("select"))
                deselect_all_action.triggered.connect(
                    lambda: apply_selection("deselect")
                )
                invert_action.triggered.connect(lambda: apply_selection("invert"))

                menu.exec_(event.globalPos())
                return

        # --- Normal filter handling (funnels etc.) ---
        if logicalIndex not in self.unique_vals:
            super().mousePressEvent(event)
            return

        # (funnel detection as before)
        icon_rect = QRect(
            self.sectionViewportPosition(logicalIndex)
            + self.sectionSize(logicalIndex)
            - self.ICON_SIZE
            - 4,
            (self.height() - self.ICON_SIZE) // 2,
            self.ICON_SIZE,
            self.ICON_SIZE,
        )
        if icon_rect.contains(event.pos()):
            self._show_filter_menu(logicalIndex, event.globalPos())
            return

        super().mousePressEvent(event)

    def _show_filter_menu(self, col, global_pos):
        uniq = self.unique_vals[col]
        curr = self.selected_vals[col]

        menu = QMenu(self)
        all_action = QAction("All", self, checkable=True)
        all_action.setChecked(curr == uniq)
        menu.addAction(all_action)
        menu.addSeparator()

        actions = []
        for val in sorted(uniq):
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
                        a.blockSignals(True)
                        a.setChecked(True)
                        a.blockSignals(False)
                else:
                    selected = set()
                    for a in actions:
                        a.blockSignals(True)
                        a.setChecked(False)
                        a.blockSignals(False)
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

    # Convenience for external callers if needed
    def clear_all(self):
        for col in list(self.selected_vals.keys()):
            self.selected_vals[col] = set(self.unique_vals[col])
        self.proxy.clear_all_filters()
        self.viewport().update()


# -------------------------------------------------------------------
# Main Window
# -------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, df):
        super().__init__()
        self.setWindowTitle("FuvestXML Browser")

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

        export_btn = QPushButton("Export Selected")
        ctrl_layout.addWidget(export_btn)

        self.model = DataFrameModel(df)
        self.proxy = MultiColumnFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table = QTableView()
        self.table.setModel(self.proxy)

        # Hide technical columns in the *view*
        header_map = {
            self.model.headerData(i, Qt.Horizontal): i
            for i in range(self.model.columnCount())
        }
        for colname in ["question_text", "source_file"]:
            if colname in header_map:
                self.table.hideColumn(header_map[colname])

        # Install the header (pass the table so header can align to the view)
        self.header = FilterHeader(self.table, self.proxy, self.table)
        self.table.setHorizontalHeader(self.header)

        # Build maps now that columns are final
        self.header.rebuild()

        # self.table = QTableView()
        # self.table.setModel(self.proxy)

        # # Hide unwanted columns
        # header_map = {self.model.headerData(i, Qt.Horizontal): i
        #             for i in range(1, self.model.columnCount())}
        # for colname in ["question_text", "source_file"]:
        #     if colname in header_map:
        #         self.table.hideColumn(header_map[colname])

        # self.header = FilterHeader(df, self.proxy, self.table)
        # self.table.setHorizontalHeader(self.header)

        left_layout.addWidget(self.table)
        splitter.addWidget(left)

        # RIGHT: HTML tabs
        tabs = QTabWidget()
        # self.html_code = QPlainTextEdit()
        # self.html_code.setReadOnly(True)

        self.html_code = QPlainTextEdit()
        self.html_code.setReadOnly(True)
        self.html_code.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Attach syntax highlighter
        self.highlighter = XMLHighlighter(self.html_code.document())
        tabs.addTab(self.html_code, "XML Code")

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
        export_btn.clicked.connect(self.export_selected)

        def clear_all():
            self.header.proxy.clear_all_filters()
            self.header.viewport().update()
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

    def export_selected(self):
        df_selected = self.model.get_selected_rows()
        if df_selected.empty:
            QMessageBox.warning(self, "Export", "No rows selected!")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Selected", "", "XML Files (*.xml)"
        )
        if not path:
            return

        # Helper: get local tag name (ignore namespaces if any)
        def local_tag(tag_or_elem):
            t = tag_or_elem.tag if hasattr(tag_or_elem, "tag") else str(tag_or_elem)
            return t.split("}", 1)[1] if "}" in t else t

        # Helper: deep copy element
        def deep_copy(elem):
            return etree.fromstring(etree.tostring(elem))

        try:
            # ---- Exam metadata from first selected row ----
            first = df_selected.iloc[0]
            exam_name = str(first.get("exam_name", "") or "")
            exam_year = str(first.get("year", "") or "")
            exam_phase = str(first.get("phase", "") or "")

            # Try to fetch 'variation' from the first source file (fallback to "")
            variation = ""
            try:
                first_tree = etree.parse(
                    first["source_file"], etree.XMLParser(recover=True)
                )
                variation = first_tree.getroot().get("variation", "") or ""
            except Exception:
                pass

            # ---- Output root <exam> ----
            root_out = etree.Element(
                "exam",
                name=exam_name,
                year=exam_year,
                phase=exam_phase,
                variation=variation,
            )

            # ---- Group selected rows by source file for stable doc order per file ----
            # We’ll rebuild groups in the order they appear in each original file.
            by_file = {}
            for _, row in df_selected.iterrows():
                src = row["source_file"]
                by_file.setdefault(src, []).append(row)

            # Process files in filename order for stability
            for src_file in sorted(by_file.keys()):
                rows = by_file[src_file]

                # Build a quick lookup of selected questions in this file:
                # key = (qtype, qnum as str)
                wanted = set()
                for r in rows:
                    qtype = str(r["question_type"])
                    qnum = str(r.get("question_number", "") or "")
                    wanted.add((qtype, qnum))

                # Parse source
                parser = etree.XMLParser(recover=True)
                try:
                    tree = etree.parse(src_file, parser)
                except Exception as e:
                    print(f"[WARN] Could not parse {src_file}: {e}")
                    continue
                root = tree.getroot()

                # Iterate question_groups in original order
                for qg in root.findall(".//question_group"):
                    # Collect selected question elements from this group in original order
                    selected_children = []
                    context_elem = None

                    for child in qg:
                        tag = local_tag(child)
                        if tag == "context":
                            context_elem = child
                        elif tag in ("objective_question", "discursive_question"):
                            # Match by id or number
                            qid = child.get("id")
                            qnum = child.get("number")
                            # We normalize to the same key that 'wanted' uses
                            if (tag, str(qid or "")) in wanted or (
                                tag,
                                str(qnum or ""),
                            ) in wanted:
                                selected_children.append(child)

                    # If this group contributes any selected questions, create an out group
                    if selected_children:
                        out_group = etree.Element("question_group")
                        # Copy group attributes, if any (like id/title)
                        for k, v in qg.attrib.items():
                            out_group.set(k, v)

                        # Copy context first (if present)
                        if context_elem is not None:
                            out_group.append(deep_copy(context_elem))

                        # Append selected questions in original order
                        for qelem in selected_children:
                            out_group.append(deep_copy(qelem))

                        # Add this group to the output exam
                        root_out.append(out_group)

            # ---- Write file ----
            tree_out = etree.ElementTree(root_out)
            tree_out.write(
                path, encoding="utf-8", pretty_print=True, xml_declaration=True
            )

            # ---- Validate against XSD (always save; warn if invalid) ----
            try:
                with open("./xsd/fuvest_xml.xsd", "rb") as f:
                    schema_root = etree.XML(f.read())
                schema = etree.XMLSchema(schema_root)
                etree.parse(path, etree.XMLParser(schema=schema))
                QMessageBox.information(
                    self,
                    "Export",
                    f"Exported {len(df_selected)} question(s) to:\n{path}\n\n✅ Schema validation passed.",
                )
            except etree.XMLSyntaxError as e:
                QMessageBox.warning(
                    self,
                    "Export Validation",
                    f"File exported to {path}, but schema validation failed:\n{e}",
                )

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

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
        header_map = {
            self.model.headerData(i, Qt.Horizontal): i
            for i in range(1, self.model.columnCount())
        }

        def cell(col_name, default=""):
            ci = header_map.get(col_name)
            return (
                self.model.item(r, ci).text()
                if ci is not None and self.model.item(r, ci)
                else default
            )

        # Expected columns from your get_dataframe(): adjust names if yours differ
        source_file = cell("source_file")
        qtype = cell("question_type")
        qnumber = cell("question_number")

        # Locate the exact question element using full XPath
        elem = find_question_element(source_file, qtype, qnumber)

        # Original XML (pretty) for the Code tab
        if elem is not None:
            xml_pretty = etree.tostring(elem, pretty_print=True, encoding="unicode")
        else:
            xml_pretty = "Question not found."

        # Show pretty XML in Code tab
        self.html_code.setPlainText(xml_pretty)
        self.html_code.setLineWrapMode(QPlainTextEdit.NoWrap)  # avoid wrapped lines
        self.html_code.setTabStopDistance(
            4 * self.html_code.fontMetrics().horizontalAdvance(" ")
        )  # 4 spaces for tabs

        # Rendered HTML for the preview tab
        html_rendered_old = xml_to_html(elem)
        print(etree.tostring(elem))
        print(html_rendered_old)

        # Processor
        xml_converter = fuvestxml.XmlConverter(fuvestxml.HtmlWriter())

        # Store the graphics_dir path on the global variable
        xml_converter.global_graphics_dir = Path("./images/")
        xml_text = (
            """<exam name="FUVEST" year="2025" phase="objective" day="1" variation="V1" date="2024-11-17" lang="pt-br">\n"""
            + "<question_group>"
            + etree.tostring(elem).decode("utf-8")
            + "</question_group>\n"
            + "</exam>\n"
        )

        print(xml_text)
        root = etree.fromstring(xml_text)

        # Load the input XML and validate
        xml_converter.read_xml_from_memory(root)
        # xml_converter.validate_xml(Path("./xsd/fuvest_xml.xsd"))

        # Create the document code
        html_rendered = xml_converter.create_document()
        print(html_rendered)
        # # select the console or file output
        # if args.print:
        #     print(tex)

        # else:
        #     args.out.write_text(tex, encoding="utf-8")
        #     print("Wrote LaTeX to", args.out)

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
