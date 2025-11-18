#!/usr/bin/env python3
"""
Initialize a SQLite database if the file does not exist.

Usage:
    python init_db.py --db mydata.db
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
from typing import Iterable, Tuple

import os
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import random


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


def db_file_exists(db_path: Path) -> bool:
    """Return True if the SQLite file already exists on disk."""
    return db_path.exists() and db_path.is_file()


def connect(db_path: Path) -> sqlite3.Connection:
    # isolation_level=None → autocommit off by default (we'll use explicit transactions)
    conn = sqlite3.connect(db_path.as_posix())
    # Nice defaults
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create example tables (idempotent: uses IF NOT EXISTS)."""
    conn.executescript(
        """
        BEGIN;

        CREATE TABLE IF NOT EXISTS questions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exam        TEXT NOT NULL,
            year        TEXT NOT NULL,
            number      TEXT NOT NULL,
            subject     TEXT NOT NULL,
            text        TEXT NOT NULL
        );

        COMMIT;
        """
    )


def seed_data(conn: sqlite3.Connection) -> None:
    """Insert some initial rows (only if tables are empty)."""
    # Only seed if no rows yet
    # people_count = conn.execute("SELECT COUNT(*) FROM people;").fetchone()[0]
    # if people_count == 0:
    #     people_rows: Iterable[Tuple[str, str]] = [
    #         ("Ada Lovelace", "ada@example.com"),
    #         ("Alan Turing", "alan@example.com"),
    #         ("Grace Hopper", "grace@example.com"),
    #     ]
    #     conn.executemany("INSERT INTO people (name, email) VALUES (?, ?);", people_rows)

    # projects_count = conn.execute("SELECT COUNT(*) FROM projects;").fetchone()[0]
    # if projects_count == 0:
    #     # Map owner emails to IDs to keep the example clean
    #     email_to_id = {
    #         email: pid
    #         for pid, email in conn.execute("SELECT id, email FROM people;").fetchall()
    #     }

    project_rows: Iterable[Tuple[str, int]] = [
        ("Fuvest", "2025", "01", "texto"),
        ("Fuvest", "2025", "01", "texto2"),
        ("Fuvest", "2025", "01", "texto3"),
        ("Fuvest", "2025", "01", "texto4"),
    ]
    # Filter any None owner_id just in case
    # project_rows = [(n, oid) for n, oid in project_rows if oid is not None]

    conn.executemany(
        "INSERT INTO questions (exam, year, number, subject, text) VALUES (?, ?, ?, ?, ?);",
        project_rows,
    )


def inner_xml(element):
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(ET.tostring(child, encoding="unicode"))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


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


def shuffle(q):
    # Step 1: Extract option children and their positions
    option_positions = []
    option_nodes = []

    options = q.find("./options")

    for i, child in enumerate(options):
        if child.tag == "option":
            option_positions.append(i)
            option_nodes.append(child)

    # Step 2: Shuffle the option nodes
    random.shuffle(option_nodes)

    # Step 3: Reinsert shuffled options at their original positions
    for pos, node in zip(option_positions, option_nodes):
        print(pos, number_to_letter(pos + 1))
        print(ET.tostring(node, encoding="unicode"))
        node.set("label", number_to_letter(pos + 1))
        options[pos] = node


def process_question_group(conn: sqlite3.Connection, data, parent):
    obj_questions = parent.findall("./objective_question")
    questions = []
    for q in obj_questions:
        # print("===================================================================")
        number = q.get("number", "").strip()
        sucess_rate = q.get("success_rate", "").strip()

        print(number)
        # print(ET.tostring(q, encoding="unicode"))
        # shuffle(q)
        # print("-----------------------------------")
        # print(ET.tostring(q, encoding="unicode"))

        # get the classification
        classif = q.find("./classification").get("subject", "").strip()
        # print(classif)

        # qstr = ET.tostring(q, encoding="unicode")
        qstr = inner_xml_clean(q)
        # print(qstr)
        questions.append((data[0], data[1], number, classif, qstr))

    conn.executemany(
        "INSERT INTO questions (exam, year, number, subject, text) VALUES (?, ?, ?, ?, ?);",
        questions,
    )


def process_xml_files_in_directory(conn: sqlite3.Connection, directory_path):
    """
    Iterates through a specified directory, finds all XML files,
    and processes each one.
    """
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
                            process_question_group(conn, data, sub_child)

                    elif child.tag == "question_group":
                        # body.append(self.render_question_group(child))
                        # qstr = ET.tostring(child, encoding="unicode")
                        # print(qstr)
                        process_question_group(conn, data, child)

                    else:
                        raise ValueError("Tag not recognized!")

                # Ending
                # body.append(self.writer.body_end())

            except ET.ParseError as e:
                print(f"Error parsing XML file {filename}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred with file {filename}: {e}")


DEFAULT_DB_PATH = Path("./output/example.db")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create & seed a SQLite DB if missing.")
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    return p.parse_args()


#########1#########2#########3#########4#########5#########6#########7#########8#########9########10#######11#########12#########
# read_parser_arguments()


def read_parser_arguments():
    parser = argparse.ArgumentParser()

    parser = argparse.ArgumentParser(
        description="Create & seed a SQLite DB if missing."
    )

    # parser.add_argument(
    #     "--create_db",
    #     type=Path,
    #     default=None,
    #     help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    # )

    parser.add_argument(
        "-c", "--create_db", action="store_true", help="Enable verbose output."
    )

    parser.add_argument(
        "-y",
        "--year",
        type=int,
        default=None,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )

    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default=None,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )

    parser.add_argument(
        "-s",
        "--subject",
        type=str,
        default=None,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    # parser.add_argument("xml", type=Path, help="Input XML file")

    # parser.add_argument(
    #     "out",
    #     type=Path,
    #     nargs="?",
    #     help="Output file path (.tex or .html). "
    #     "If not supplied, it will be derived from input name.",
    # )

    # parser.add_argument(
    #     "-v", "--verbose", action="store_true", help="Enable verbose output."
    # )

    # parser.add_argument(
    #     "-p", "--print", action="store_true", help="Enable verbose output."
    # )

    parser.add_argument("-f", "--no-fix", action="store_true", help="Fix numbering.")

    # fmt_group = parser.add_mutually_exclusive_group()
    # fmt_group.add_argument(
    #     "--latex", action="store_true", help="Generate LaTeX output (default)"
    # )
    # fmt_group.add_argument("--html", action="store_true", help="Generate HTML output")

    # parser.add_argument(
    #     "--schema",
    #     type=Path,
    #     default=Path("./xsd/fuvest_xml.xsd"),
    #     help="Path to XML Schema file (default: ./xsd/fuvest_xml.xsd)",
    # )

    # parser.add_argument(
    #     "--graphics-dir",
    #     type=Path,
    #     default=Path("../images/"),
    #     help="Base directory for image sources (default: ../images/)",
    # )

    # parser.add_argument(
    #     "--output-dir",
    #     type=Path,
    #     default=Path("./output/"),
    #     help="Directory to place the output file (default: ./output/",
    # )

    return parser.parse_args()


def fetch_by_year(year):
    """
    Fetches all products that match a specific category.
    """
    try:
        with sqlite3.connect(DEFAULT_DB_PATH) as conn:
            cursor = conn.cursor()

            # This is the SQL query with a 'WHERE' clause.
            # The '?' is a placeholder for our criteria.
            query = "SELECT * FROM questions WHERE year = ?"

            # Execute the query, passing the criteria as a tuple.
            # This is the safe way to prevent SQL injection.
            cursor.execute(query, (year,))

            # Get all matching rows
            results = cursor.fetchall()

            if not results:
                print("No products found for this category.")
                return

            # Loop through and print the results
            ret = []
            for row in results:
                ret.append(
                    {
                        "id": row[0],
                        "exam": row[1],
                        "year": row[2],
                        "number": row[3],
                        "subject": row[4],
                        "text": row[5],
                    }
                )

            return ret

    except sqlite3.Error as e:
        print(f"An error occurred while fetching data: {e}")


def fetch_by_name(name):
    """
    Fetches all products that match a specific category.
    """
    try:
        with sqlite3.connect(DEFAULT_DB_PATH) as conn:
            cursor = conn.cursor()

            # This is the SQL query with a 'WHERE' clause.
            # The '?' is a placeholder for our criteria.
            query = "SELECT * FROM questions WHERE exam = ?"

            # Execute the query, passing the criteria as a tuple.
            # This is the safe way to prevent SQL injection.
            cursor.execute(query, (name,))

            # Get all matching rows
            results = cursor.fetchall()

            if not results:
                print("No products found for this category.")
                return

            # Loop through and print the results
            ret = []
            for row in results:
                ret.append(
                    {
                        "id": row[0],
                        "exam": row[1],
                        "year": row[2],
                        "number": row[3],
                        "subject": row[4],
                        "text": row[5],
                    }
                )

            return ret

    except sqlite3.Error as e:
        print(f"An error occurred while fetching data: {e}")


def fetch_by_subject(subject):
    """
    Fetches all products that match a specific category.
    """
    try:
        with sqlite3.connect(DEFAULT_DB_PATH) as conn:
            cursor = conn.cursor()

            # This is the SQL query with a 'WHERE' clause.
            # The '?' is a placeholder for our criteria.
            query = "SELECT * FROM questions WHERE subject LIKE ?;"

            # Execute the query, passing the criteria as a tuple.
            # This is the safe way to prevent SQL injection.
            cursor.execute(query, (subject + "%",))
            # cursor.execute(query, (search_term + '%',))

            # Get all matching rows
            results = cursor.fetchall()

            if not results:
                print("No products found for this category.")
                return

            # Loop through and print the results
            ret = []
            for row in results:
                ret.append(
                    {
                        "id": row[0],
                        "exam": row[1],
                        "year": row[2],
                        "number": row[3],
                        "subject": row[4],
                        "text": row[5],
                    }
                )

            return ret

    except sqlite3.Error as e:
        print(f"An error occurred while fetching data: {e}")


def main() -> None:
    # Process the input arguments
    args = read_parser_arguments()

    # create database
    if args.create_db:
        db_path = Path(DEFAULT_DB_PATH)
        if db_path.exists():
            print(f"⚠ Existing database found. Deleting: {db_path}")
            # If the database file already exists, it is deleted first (Path.unlink()).
            db_path.unlink()

        # Ensure parent directories exist
        db_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"⏳ Creating new database at: {db_path}")
        with connect(db_path) as conn:
            try:
                create_schema(conn)

                # Specify the directory containing your XML files
                target_directory = "./exams/"  # Replace with your actual directory

                process_xml_files_in_directory(conn, target_directory)

                # seed_data(conn)
                conn.commit()
            except Exception:
                # On any error, rollback and remove the half-created file for cleanliness
                conn.rollback()
                try:
                    db_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise
    else:
        print(
            "#############################################################################################################"
        )
        year = args.year
        name = args.name
        subject = args.subject
        print(name, year, subject, args.output)

        questions = []
        if args.year:
            questions = fetch_by_year(year)

        elif args.subject:
            questions = fetch_by_subject(subject)

        elif args.name:
            questions = fetch_by_name(name)

        # print(questions)
        if args.output:
            print("BINGO", args.output)
            with open(args.output, "w", encoding="utf-8") as file:
                file.write('<?xml version="1.0" encoding="utf-8"?>\n')
                file.write(
                    '<exam name="FUVEST" year="2025" phase="objective" day="1" variation="V1" date="2024-11-17" lang="pt-br">\n'
                )
                for i, q in enumerate(questions):
                    file.write("<question_group>\n")
                    file.write(f'<objective_question number="{i + 1}">\n')
                    file.write(q["text"])
                    file.write("</objective_question>\n")
                    file.write("</question_group>\n")
                file.write("</exam>\n")
                # file.write("This is the second line.")
        else:
            for q in questions:
                # row is a tuple: (id, name, category, price)
                # print(
                #     f"  ID: {row[0]}, Exam: {row[1]}, Year: {row[2]}, Number: {row[3]}, Subject: {row[4]}, text: {row[5]}"
                # )
                print(
                    f"ID: {q['id']}, Exam: {q['exam']}, Year: {q['year']}, Number: {q['number']}, Subject: {q['subject']}, text: {q['text']}"
                )
    # if db_file_exists(db_path):
    #     print(f"✔ Database already exists: {db_path}")
    #     return

    # print("✅ Database created and populated successfully.")
    # print("   Try it out:")
    # print(
    #     f'      sqlite3 {db_path} "SELECT p.name, pr.name FROM people p JOIN projects pr ON pr.owner_id = p.id;"'
    # )


if __name__ == "__main__":
    main()
