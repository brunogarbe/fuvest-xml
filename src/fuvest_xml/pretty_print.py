import xml.etree.ElementTree as ET
import typer

app = typer.Typer(help="Format a Fuvest XML file in place.")

def pretty_print_xml(file_path):
    """
    Pretty prints an XML file in-place according to specific rules.

    - Adds a newline between <context> and the first <question> tag.
    - Adds a newline between <question> tags within a <question_group> if there's more than one.
    - Adds a newline between <question_group> tags.

    Args:
        file_path (str): The path to the XML file.
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # First, apply a generic indentation to the whole tree.
        indent(root)

        # Second, add extra newlines where specified by post-processing the tree.

        # 1. Add newlines between <question> tags within a <question_group>
        for group in root.findall('.//question_group'):
            questions = group.findall('objective_question')
            if len(questions) > 1:
                for i in range(len(questions) - 1):
                    # Prepend a newline to the existing tail (which now contains indentation)
                    if questions[i].tail:
                        questions[i].tail = "\n" + questions[i].tail
                        
            questions = group.findall('discursive_question')
            if len(questions) > 1:
                for i in range(len(questions) - 1):
                    # Prepend a newline to the existing tail (which now contains indentation)
                    if questions[i].tail:
                        questions[i].tail = "\n" + questions[i].tail

        # 2. Add newlines between <question_group> tags.
        # We must iterate through the possible parents (<exam> and <subject>)
        # to handle groups of siblings correctly.
        potential_parents = root.findall('.//subject')
        potential_parents.append(root) # The root <exam> tag can also be a parent
        
        for parent in potential_parents:
            groups = parent.findall('question_group')
            if len(groups) > 1:
                for i in range(len(groups) - 1):
                     if groups[i].tail:
                        groups[i].tail = "\n" + groups[i].tail
        
        # 3. Add newline between the last <context> and the first <question> in a group
        for group in root.findall('.//question_group'):
            contexts = group.findall('context')
            # Check if there is at least one context tag
            if contexts:
                # Get the last context tag
                last_context = contexts[-1]
                if last_context.tail:
                    last_context.tail = "\n" + last_context.tail
        
        # Write the changes back to the same file
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        print(f"Successfully pretty-printed '{file_path}'")

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except ET.ParseError as e:
        print(f"Error parsing XML file: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def indent(elem, level=0):
    """
    Recursively adds indentation to the XML tree.
    """
    i = "\n" + level*"\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for subelem in elem:
            indent(subelem, level+1)
        if not subelem.tail or not subelem.tail.strip():
            subelem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

@app.command()
def format_command(
    xml: str = typer.Argument(..., help="XML file to format."),
) -> None:
    pretty_print_xml(xml)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
