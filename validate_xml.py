import argparse
import glob
import os
from lxml import etree

def load_valid_subjects(file_path):
    subjects = set()
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):  # permite comentários
                subjects.add(line)
    return subjects


def validate_xml(schema_file, xml_file):
    # Carrega schema
    with open(schema_file, 'rb') as f:
        schema_doc = etree.XML(f.read())
    schema = etree.XMLSchema(schema_doc)

    parser = etree.XMLParser(schema=schema)

    try:
        tree = etree.parse(xml_file, parser)
    except etree.XMLSyntaxError as e:
        print(f"[ERROR] {xml_file}: inválido contra o XSD\n{e}")
        return False

    root = tree.getroot()

    # 1. Verificar incremento de <question number="">
    question_numbers = []
    for q in root.xpath("//question"):
        try:
            num = int(q.get("number"))
            question_numbers.append(num)
        except (TypeError, ValueError):
            print(f"[ERROR] {xml_file}: question sem número válido -> {etree.tostring(q, pretty_print=True).decode()}")
            return False

    expected = list(range(1, len(question_numbers) + 1))
    if question_numbers != expected:
        print(f"[ERROR] {xml_file}: sequência incorreta de <question number>. Esperado {expected}, encontrado {question_numbers}")
        return False

    # 2. Verificar subjects válidos
    # for subj in root.xpath("//classification/subject"):
        # text = subj.text.strip()
        # if text not in valid_subjects:
            # print(f"[ERROR] {xml_file}: subject inválido '{text}'")
            # return False

    print(f"[OK] {xml_file} válido e consistente ✅")
    return True


def main():
    parser = argparse.ArgumentParser(description="Valida XML contra XSD e regras extras")
    parser.add_argument("schema", help="Arquivo XSD para validação")
    parser.add_argument("xml", help="Arquivo XML ou máscara (*.xml)")
    #parser.add_argument("subjects", help="Arquivo de texto com lista de subjects válidos (um por linha)")
    args = parser.parse_args()

    # if not os.path.exists(args.subjects):
        # print(f"Arquivo de subjects não encontrado: {args.subjects}")
        # return

    #valid_subjects = load_valid_subjects(args.subjects)

    files = glob.glob(args.xml)
    if not files:
        print(f"Nenhum arquivo encontrado para {args.xml}")
        return

    for file in files:
        validate_xml(args.schema, file)


if __name__ == "__main__":
    main()
