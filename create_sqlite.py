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


def process_question_group(conn: sqlite3.Connection, data, parent):
    obj_questions = parent.findall("./objective_question")
    questions = []
    for q in obj_questions:
        number = q.get("number", "").strip()
        sucess_rate = q.get("success_rate", "").strip()

        # get the classification
        classif = q.find("./classification").get("subject", "").strip()
        print(classif)

        qstr = ET.tostring(q, encoding="unicode")
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


def main() -> None:
    args = parse_args()
    db_path: Path = args.db

    if db_file_exists(db_path):
        print(f"✔ Database already exists: {db_path}")
        return

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

    # print("✅ Database created and populated successfully.")
    # print("   Try it out:")
    # print(
    #     f'      sqlite3 {db_path} "SELECT p.name, pr.name FROM people p JOIN projects pr ON pr.owner_id = p.id;"'
    # )


if __name__ == "__main__":
    main()
