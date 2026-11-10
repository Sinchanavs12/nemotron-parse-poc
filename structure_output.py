
import json
import re
import os
import glob

# ==========================================
# CONFIGURATION
# ==========================================

INPUT_FOLDER = "outputs"
OUTPUT_FOLDER = "outputs/structured"
IMAGE_FOLDER = "outputs/images"
PDF_NAME = "sample.pdf"


# ==========================================
# STEP 1: PARSE CHART CONTENT
# ==========================================

def parse_chart_content(content):

    chart_match = re.search(
        r'<chart\s+type="([^"]+)">',
        content
    )

    chart_type = chart_match.group(1) if chart_match else "unknown"

    chart_details = {
        "chart_type": chart_type,
        "x_axis": None,
        "y_axis": None,
        "legend_items": [],
        "data": []
    }

    x_match = re.search(r"axis\[x\]:\s*(.*)", content)
    y_match = re.search(r"axis\[y\]:\s*(.*)", content)

    if x_match:
        chart_details["x_axis"] = x_match.group(1).strip()

    if y_match:
        chart_details["y_axis"] = y_match.group(1).strip()

    legend_match = re.search(
        r"legend\[[^\]]+\]:\s*items=(.*)",
        content
    )

    if legend_match:
        chart_details["legend_items"] = [
            item.strip()
            for item in legend_match.group(1).split(";")
        ]

    # Extract Markdown table from chart content
    table_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("|")
    ]

    if len(table_lines) >= 2:

        headers = [
            value.strip()
            for value in table_lines[0].strip("|").split("|")
        ]

        for line in table_lines[1:]:

            # Skip Markdown separator rows
            if re.fullmatch(r"[\s|:-]+", line):
                continue

            values = [
                value.strip()
                for value in line.strip("|").split("|")
            ]

            if len(values) != len(headers):
                continue

            row = {}

            for header, value in zip(headers, values):

                try:
                    number = float(value)
                    if number.is_integer():
                        number = int(number)
                    row[header] = number

                except ValueError:
                    row[header] = value

            chart_details["data"].append(row)

    return chart_details


# ==========================================
# STEP 2: PARSE NEMOTRON OUTPUT
# ==========================================

def parse_nemotron_output(input_file, page_number):

    with open(input_file, "r", encoding="utf-8") as file:
        response = json.load(file)

    raw_content = response.get("content", "")

    elements = []
    unparsed_blocks = []

    # Match complete Nemotron layout blocks.
    # Unlike split("\n\n"), this also handles
    # multiline chart content.

    pattern = re.compile(
        r"<x_([\d.]+)><y_([\d.]+)>(.*?)"
        r"<x_([\d.]+)><y_([\d.]+)>"
        r"<class_([A-Za-z-]+)>",
        re.DOTALL
    )

    matches = list(pattern.finditer(raw_content))

    cursor = 0

    for match in matches:

        # Preserve any content that could not be matched
        unmatched = raw_content[cursor:match.start()].strip()

        if unmatched:
            unparsed_blocks.append(unmatched)

        x_start, y_start, content, x_end, y_end, element_type = (
            match.groups()
        )

        element_type = element_type.lower().replace("-", "_")
        content = content.strip()

        # Remove leading Markdown heading symbols
        content = re.sub(r"^#+\s*", "", content)

        element = {
            "type": element_type,
            "content": content,
            "coordinates": {
                "x_start": float(x_start),
                "y_start": float(y_start),
                "x_end": float(x_end),
                "y_end": float(y_end)
            }
        }

        # Preserve original page image reference
        if element_type == "picture":
            element["image_reference"] = (
                f"{IMAGE_FOLDER}/page_{page_number}.png"
            )

        # Extract additional structured chart information
        if element_type == "chart":
            element["chart_details"] = parse_chart_content(content)

        elements.append(element)

        cursor = match.end()

    # Check remaining content after the last match
    remaining = raw_content[cursor:].strip()

    if remaining:
        unparsed_blocks.append(remaining)

    validation = {
        "total_blocks": len(elements) + len(unparsed_blocks),
        "parsed_blocks": len(elements),
        "unparsed_blocks": len(unparsed_blocks),
        "all_blocks_parsed": len(unparsed_blocks) == 0,
        "finish_reason": response.get("finish_reason")
    }

    return {
        "document": PDF_NAME,
        "page_number": page_number,
        "elements": elements,
        "validation": validation,
        "unparsed_content": unparsed_blocks,
        "metadata": {
            "finish_reason": response.get("finish_reason"),
            "usage": response.get("usage")
        }
    }


# ==========================================
# STEP 3: PROCESS ALL RAW JSON FILES
# ==========================================

def process_all_pages():

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    input_files = glob.glob(
        os.path.join(INPUT_FOLDER, "page_*.json")
    )

    input_files.sort(
        key=lambda path: int(
            re.search(r"page_(\d+)\.json$", path).group(1)
        )
    )

    if not input_files:
        print("No Nemotron JSON files found!")
        return

    successful_pages = 0
    failed_pages = 0

    print(f"\nFound {len(input_files)} page response files.\n")

    for input_file in input_files:

        filename = os.path.basename(input_file)

        page_number = int(
            re.search(r"page_(\d+)\.json$", filename).group(1)
        )

        output_file = os.path.join(
            OUTPUT_FOLDER,
            f"page_{page_number}_structured.json"
        )

        print(f"Processing page {page_number}...")

        try:

            structured_data = parse_nemotron_output(
                input_file,
                page_number
            )

            with open(output_file, "w", encoding="utf-8") as file:
                json.dump(
                    structured_data,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

            validation = structured_data["validation"]

            if validation["all_blocks_parsed"]:
                successful_pages += 1
                status = "SUCCESS"
            else:
                failed_pages += 1
                status = "WARNING"

            print(
                f"{status} | Page {page_number} | "
                f"Elements: {len(structured_data['elements'])} | "
                f"Unparsed: {validation['unparsed_blocks']}"
            )

        except Exception as error:

            failed_pages += 1
            print(f"ERROR | Page {page_number} | {error}")

    print("\n========== PROCESSING SUMMARY ==========")
    print("Total files found:", len(input_files))
    print("Successful pages:", successful_pages)
    print("Failed or warning pages:", failed_pages)
    print("Output folder:", OUTPUT_FOLDER)
    print("========================================")


if __name__ == "__main__":
    process_all_pages()