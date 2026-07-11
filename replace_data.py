
if __name__ == "__main__":

    target_file = "exams\\fuvest_2021_fase_01.xml"
    data_file = "exams\\2021.txt"
    output_file = "output.txt"
    
    # Load new data into a dictionary
    replacements = []
    with open(data_file, 'r', encoding='utf-8') as df:
        for line in df:
            line = line.strip()
            replacements.append(line)

    # Process the target file
    output_lines = []
    counter = 0
    with open(target_file, 'r', encoding='utf-8') as tf:
        for line_num, line in enumerate(tf, start=1):
            stripped = line.strip()
            #if not stripped:
            #    output_lines.append(line)
            #    continue

            if stripped.startswith('<classification') == True:
                print(f"Replacing line {line_num} with {counter}: '{line.strip()}' → '{replacements[counter]}'")
                output_lines.append('<classification subject="' + replacements[counter] +  '" />\n')
                counter = counter + 1
            else:
                output_lines.append(line)

    # Write to output file
    with open(output_file, 'w', encoding='utf-8') as of:
        of.writelines(output_lines)

    print(f"\n✅ Output written to '{output_file}'")