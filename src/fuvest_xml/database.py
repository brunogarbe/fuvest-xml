#!/usr/bin/env python3
"""
Initialize a SQLite database if the file does not exist.

Usage:
    python init_db.py --db mydata.db
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable, Optional, Tuple

import os
import xml.etree.ElementTree as ET
from datetime import datetime
import re
from . import convert as fuvestxml
from tabulate import tabulate
import typer

app = typer.Typer(help="Create, query, and export the Fuvest XML database.")

DEFAULT_DB_PATH = Path("./output/fuvestxml.db")


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# search_database
#
def db_file_exists(db_path: Path) -> bool:
    """Return True if the SQLite file already exists on disk."""
    return db_path.exists() and db_path.is_file()


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# connect
#
def connect(db_path: Path) -> sqlite3.Connection:
    # isolation_level=None → autocommit off by default (we'll use explicit transactions)
    conn = sqlite3.connect(db_path.as_posix())
    # sqlite3.connect(DEFAULT_DB_PATH)
    # Nice defaults
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# create_schema
#
def create_schema(conn: sqlite3.Connection) -> None:
    """Create example tables (idempotent: uses IF NOT EXISTS)."""
    conn.executescript(
        """
        BEGIN;

        CREATE TABLE IF NOT EXISTS schema (
            key     TEXT NOT NULL,
            value   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS exams (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS contexts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            context     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS questions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id     INTEGER,
            year        TEXT NOT NULL,
            number      TEXT NOT NULL,
            type        INTEGER,
            sucess_rate INTEGER,
            cancelled   BOOLEAN,
            subject_id  INTEGER,
            context_id  INTEGER,
            statement   TEXT NOT NULL
        );

        COMMIT;
        """
    )

    # CREATE INDEX idx_subject ON questions(subject);


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# inner_xml
#
def inner_xml(element):
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(ET.tostring(child, encoding="unicode"))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# inner_xml_clean
#
def inner_xml_clean(element):
    """
    Return the inner XML of an element as a string,
    removing unnecessary whitespace and indentation.
    """
    parts = []

    if element.text and element.text.strip():
        parts.append(element.text.strip())

    for child in element:
        parts.append(ET.tostring(child, encoding="unicode").strip())
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())

    # Join parts and collapse multiple spaces/newlines
    xml_text = " ".join(parts)
    xml_text = re.sub(r"\s+", " ", xml_text).strip()
    return xml_text


def insert_meta(cursor, key, value):
    cursor.execute(
        f"INSERT INTO schema (key, value) VALUES (?, ?)",
        (
            key,
            value,
        ),
    )


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# get_or_create_data
#
def get_or_create_data(cursor, table, value):
    """Returns the ID of a row in (table) where (column)=value.
    Creates the row if it does not exist."""
    cursor.execute(f"SELECT id FROM {table} WHERE name = ?", (value,))
    row = cursor.fetchone()

    if row:
        return row[0]

    # Insert and return new ID
    cursor.execute(
        f"INSERT INTO {table} (name) VALUES (?)",
        (value,),
    )
    return cursor.lastrowid


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# get_data
#
def get_data(cursor, table, value):
    cursor.execute(f"SELECT id FROM {table} WHERE name = ?", (value,))
    row = cursor.fetchone()

    if row:
        return row[0]

    return None


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# process_xml_files_in_directory
#
def process_xml_files(conn: sqlite3.Connection, directory_path):
    """
    Iterates through a specified directory, finds all XML files,
    and processes each one.
    """
    cursor = conn.cursor()
    for filename in os.listdir(directory_path):
        if filename.endswith(".xml"):
            file_path = os.path.join(directory_path, filename)
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()

                name = root.get("name", "Exam")
                year = root.get("year", "")
                phase = root.get("phase", "")
                day = root.get("day", "")
                variation = root.get("variation", "")

                data = (name, year)
                # Variable to store the body commands create by the render functions
                # body = []

                # Header
                # title = f"{self.writer.clean_text(name) + ' ' + self.writer.clean_text(year)}"

                # body.append(self.writer.preamble(title))
                # body.append(self.writer.body_start())

                # Iterate over the exam child tags
                for child in root:
                    if child.tag == "subject":
                        for sub_child in child:
                            # body.append(self.render_question_group(sub_child))
                            # qstr = ET.tostring(sub_child, encoding="unicode")
                            # print(qstr)
                            process_question_group(cursor, data, sub_child)

                    elif child.tag == "question_group":
                        # body.append(self.render_question_group(child))
                        # qstr = ET.tostring(child, encoding="unicode")
                        # print(qstr)
                        process_question_group(cursor, data, child)

                    else:
                        raise ValueError("Tag not recognized!")

                # Ending
                # body.append(self.writer.body_end())

            except ET.ParseError as e:
                print(f"Error parsing XML file {filename}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred with file {filename}: {e}")


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# process_question_group
#
def process_question_group(cursor, data, parent):
    context_xml = parent.find("./context")
    context_id = "Null"
    if context_xml is not None:
        # get the xml text and collapse multiple spaces/newlines
        context = ET.tostring(context_xml, encoding="unicode")
        context = re.sub(r"\s+", " ", context).strip()

        cursor.execute("INSERT INTO contexts (context) VALUES (?);", (context,))
        context_id = cursor.lastrowid

    exam = data[0]
    year = data[1]

    exam_id = get_or_create_data(cursor, "exams", exam)

    obj_questions = parent.findall("./objective_question")

    for q in obj_questions:
        # get the attributes from the xml
        number = q.get("number", "").strip()
        sucess_rate = q.get("success_rate", "").strip()
        try:
            sucess_rate = int(10 * float(sucess_rate))
        except:
            sucess_rate = "Null"

        # print(sucess_rate)
        #
        cancelled = q.get("cancelled", "false").strip()
        if cancelled == "true":
            cancelled = 1
        else:
            cancelled = 0

        # get the classification
        subject = q.find("./classification").get("subject", "").strip()
        subject_id = get_or_create_data(cursor, "subjects", subject)

        statement = inner_xml_clean(q)

        question_type = 1

        # Insert the question
        cursor.execute(
            """
            INSERT INTO questions (exam_id, year, number, type, sucess_rate, cancelled, subject_id, context_id, statement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_id,
                year,
                number,
                question_type,
                sucess_rate,
                cancelled,
                subject_id,
                context_id,
                statement,
            ),
        )


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# select_questions
#
def select_questions(
    conn,
    exam: str | None = None,
    year: int | None = None,
    subject: str | None = None,
    all_data: bool = False,
):
    """
    Select questions, optionally filtered by:
      - exam  (exam name, e.g. 'FUVEST 2024')
      - year  (exam year, e.g. 2024)
      - subject (subject name, e.g. 'Mathematics')

    Any combination of these filters is allowed.
    """

    cur = conn.cursor()

    if all_data:
        columns = """
            q.id,
            e.name  AS exam,
            q.year  AS year,
            q.number    AS number,
            s.name  AS subject,
            q.type,
            q.sucess_rate,
            q.cancelled,
            c.context  AS context,
            q.statement
            """
    else:
        columns = """
            q.id,
            e.name  AS exam,
            q.year  AS year,
            q.number    AS number,
            s.name  AS subject,
            q.type,
            q.sucess_rate,
            q.cancelled
            """

    base_query = f"""
    SELECT
        {columns}
    FROM questions q
    JOIN exams e     ON q.exam_id = e.id
    JOIN subjects s  ON q.subject_id = s.id
    LEFT JOIN contexts c   ON q.context_id = c.id
    """

    conditions = []
    params: list[object] = []

    if exam is not None:
        conditions.append("e.name = ?")
        params.append(exam)

    if year is not None:
        conditions.append("q.year = ?")
        params.append(year)

    if subject is not None:
        conditions.append("s.name LIKE ?")
        params.append(f"{subject}%")

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    base_query += "\n ORDER BY q.year, e.name, q.id;"

    # print(base_query, params)

    cur.execute(base_query, params)
    rows = cur.fetchall()
    conn.close()

    # Simple printout (optional)
    # print("Filters:", {"exam": exam, "year": year, "subject": subject})
    # print("-" * 120)
    # for row in rows:
    #     # print(
    #     #     f"[{row['number']}] Exam: {row['exam']} ({row['year']}) "
    #     #     f"| Subject: {row['subject']}\n"
    #     #     f"Context: {row['context']}\n"
    #     #     f"Statement: {row['statement']}\n" + "—" * 60
    #     # )
    #     print(row)

    # Convert rows to list of dictionaries
    rows_as_dicts = [dict(row) for row in rows]

    # print(rows_as_dicts)

    return rows_as_dicts


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# search_database
#
def export_questions(filename, questions, shu=False):
    with open(filename, "w", encoding="utf-8") as file:
        file.write('<?xml version="1.0" encoding="utf-8"?>\n')
        file.write(
            '<exam name="FUVEST" year="2025" phase="objective" day="1" variation="V1" date="2024-11-17" lang="pt-br">\n'
        )
        for i, q in enumerate(questions):
            # print(q)
            file.write("<question_group>\n")
            file.write(f'<objective_question number="{i + 1}">\n')
            if shu:
                root = ET.fromstring("<temp>" + q["statement"] + "</temp>")
                fuvestxml.shuffle_questions(root)
                qstr = inner_xml_clean(root)
                file.write(qstr)
            else:
                file.write(q["statement"])
            file.write("</objective_question>\n")
            file.write("</question_group>\n")
        file.write("</exam>\n")


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# search_database
#
def print_questions(questions, verbose=False):
    if verbose is False:
        if questions:
            # Print using tabulate
            print(tabulate(questions, headers="keys", tablefmt="simple"))
            print(f"\nTotal number of questions: {len(questions)}")
        else:
            print("No results found.")
    else:
        for q in questions:
            print(q)

    print("")


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# read_parser_arguments()
#
#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# main
#
@app.command()
def database_command(
    create_db: bool = typer.Option(False, "--create-db", "--create_db", "-c", help="Create and seed the database."),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Filter questions by year."),
    exam: Optional[str] = typer.Option(None, "--exam", "-e", help="Filter questions by exam."),
    subject: Optional[str] = typer.Option(None, "--subject", "-s", help="Filter questions by subject."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Export matching questions to this file."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show complete question data."),
    no_fix: bool = typer.Option(False, "--no-fix", "-f", help="Do not fix numbering."),
    shuffle: bool = typer.Option(False, "--shuffle", help="Shuffle exported options."),
) -> None:
    # create database
    if create_db:
        db_path = Path(DEFAULT_DB_PATH)
        if db_path.exists():
            print(f"⚠ Existing database found. Deleting: {db_path}")
            # If the database file already exists, it is deleted first (Path.unlink()).
            db_path.unlink()

        # Ensure parent directories exist
        db_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Creating new database at: {db_path}")
        with connect(db_path) as conn:
            try:
                create_schema(conn)
                cursor = conn.cursor()
                insert_meta(cursor, "info", "Qngwfw~%g~%Gwzst%Lfwgj%Ozsntw")
                insert_meta(
                    cursor, "version", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                insert_meta(cursor, "license", "AGPL-3.0")

                # Specify the directory containing your XML files
                target_directory = "./exams/"

                process_xml_files(conn, target_directory)

                conn.commit()

            except Exception:
                # On any error, rollback and remove the half-created file for cleanliness
                conn.rollback()
                try:
                    db_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise

    # search the database
    else:
        conn = connect(DEFAULT_DB_PATH)

        if output:
            questions = select_questions(
                conn,
                year=year,
                exam=exam,
                subject=subject,
                all_data=True,
            )
            export_questions(output, questions, shuffle)

        else:
            questions = select_questions(
                conn,
                year=year,
                exam=exam,
                subject=subject,
                all_data=verbose,
            )
            print_questions(questions, verbose)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
