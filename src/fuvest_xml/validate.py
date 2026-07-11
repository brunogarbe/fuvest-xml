import glob
import os
from lxml import etree
import sys
from colorama import Fore, Back, Style
from colorama import init
import typer

app = typer.Typer(help="Validate Fuvest XML against the XSD and additional rules.")

init()


def load_file_lines(path):
    """Lê todas as linhas de um arquivo e retorna lista (1-based index)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def show_context(lines, line, col, context=2):
    """Mostra trecho do XML com linha destacada."""
    start = max(0, line - context - 1)
    end = min(len(lines), line + context)
    snippet = []
    for i in range(start, end):
        prefix = ">>" if (i + 1) == line else "  "
        marker = ""
        if (i + 1) == line and col > 0 and col <= len(lines[i]) + 1:
            marker = " " * (col + 6) + "^"
        snippet.append(f"{prefix} {i + 1:4d}: {lines[i].rstrip()}")
        if marker:
            snippet.append(marker)
    return "\n".join(snippet)


def validate_xml(schema_file, xml_file, detailed=False):
    errors = []

    # Carrega schema
    with open(schema_file, "rb") as f:
        schema_doc = etree.XML(f.read())
    schema = etree.XMLSchema(schema_doc)

    try:
        # Parse sem schema (para manter localização exata)
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(xml_file, parser)

        exam = tree.xpath("//exam")[0].get("name")
        number_of_items = 4 if exam == "UNICAMP" else 5

        # Valida contra schema
        if not schema.validate(tree):
            for error in schema.error_log:
                errors.append(
                    {
                        "file": xml_file,
                        "line": error.line,
                        "column": error.column,
                        "message": error.message,
                    }
                )

        # 🔹 Checagem de numeração incremental
        question_numbers = []
        for q in tree.xpath("//objective_question"):
            try:
                num = int(q.get("number"))
                question_numbers.append((num, q.sourceline))
            except (TypeError, ValueError):
                errors.append(
                    {
                        "file": xml_file,
                        "line": q.sourceline,
                        "column": 0,
                        "message": f"<objective_question> possui atributo 'number' inválido: {q.get('number')}",
                    }
                )

            # print(num, q, q.findall("options/table"))
            if q.findall("options_table"):
                if len(q.findall("options_table/option")) != 5:
                    errors.append(
                        {
                            "file": xml_file,
                            "line": q.sourceline,
                            "column": 0,
                            "message": f"<objective_question> possui numero de items ({len(q.findall('options_table/option'))}) inválido: {q.get('number')}",
                        }
                    )
            else:
                if len(q.findall("options/option")) != number_of_items:
                    errors.append(
                        {
                            "file": xml_file,
                            "line": q.sourceline,
                            "column": 0,
                            "message": f"<objective_question> possui numero de items ({len(q.findall('options/option'))}) inválido: {q.get('number')}",
                        }
                    )
            # print(len(q.xpath("//objective_question/options/option")))
            # for opt in q.xpath("//options/option"):
            #    print(opt)

        # if question_numbers:
        #     expected = list(range(1, len(question_numbers) + 1))
        #     found = [n for n, _ in question_numbers]
        #     if found != expected:
        #         for (n, line), exp in zip(question_numbers, expected):
        #             if n != exp:
        #                 errors.append(
        #                     {
        #                         "file": xml_file,
        #                         "line": line,
        #                         "column": 0,
        #                         "message": f"Número incorreto: encontrado {n}, esperado {exp}",
        #                     }
        #                 )

    except etree.XMLSyntaxError as e:
        # Erros de parsing
        for error in e.error_log:
            errors.append(
                {
                    "file": xml_file,
                    "line": error.line,
                    "column": error.column,
                    "message": error.message,
                }
            )

    if detailed and errors:
        lines = load_file_lines(xml_file)
        for err in errors:
            if err["line"] > 0:
                err["context"] = show_context(lines, err["line"], err["column"])

    return errors


@app.command()
def validate_command(
    xml: list[str] = typer.Argument(..., help="XML file or glob pattern (for example, *.xml)."),
    schema: str = typer.Option(
        r".\xsd\fuvest_xml.xsd", "--schema", help="Path to the XSD schema."
    ),
    detailed: bool = typer.Option(
        False, "--detailed", help="Show the XML context for each error."
    ),
) -> None:
    if not os.path.exists(schema):
        typer.echo(f"[ERRO] Schema não encontrado: {schema}", err=True)
        raise typer.Exit(code=1)

    total_errors = 0
    for input_address in xml:
        files = glob.glob(input_address)
        if not files:
            typer.echo(f"[ERRO] Nenhum arquivo encontrado para '{input_address}'", err=True)
            raise typer.Exit(code=1)

        for file in files:
            errors = validate_xml(schema, file, detailed=detailed)
            if errors:
                print(f"\n[ERROS] {file}:")
                for err in errors:
                    print(
                        f"  Linha {err['line']}, Coluna {err['column']}: {err['message']}"
                    )
                    if detailed and "context" in err:
                        print(err["context"])
                        print("-" * 60)
                total_errors += len(errors)
            else:
                print(Fore.GREEN + "[OK] " + Style.RESET_ALL + f"{file} válido!")

    if total_errors > 0:
        print(f"\nTotal de erros encontrados: {total_errors}")
    else:
        print("\nTodos os arquivos são válidos!")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
