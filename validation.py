import json
import os
import re
import glob
from pathlib import Path
import pymupdf



# ==========================================
# CONFIGURATION
# ==========================================

STRUCTURED_FOLDER = "outputs/structured"
VALIDATED_FOLDER = "outputs/validated"
IMAGE_FOLDER = "outputs/images"

PDF_PATH = "samples/sample.pdf"
PDF_NAME = os.path.basename(PDF_PATH)

def check_suspicious_text(content):
    """
    Detect suspicious text patterns without assuming that
    unusual content is necessarily an extraction error.
    """
    issues = []

    if not isinstance(content, str):
        return issues

    # Check for Unicode replacement characters.
    if "\ufffd" in content:
        issues.append(
            "Text contains Unicode replacement character(s)."
        )

    # Check for unexpected non-printable control characters.
    unexpected_controls = [
        char for char in content
        if ord(char) < 32 and char not in "\n\r\t"
    ]

    if unexpected_controls:
        issues.append(
            "Text contains unexpected non-printable control characters."
        )

    # Check for unusually long repeated character sequences.
    repeated_sequences = re.findall(
        r"(.)\1{7,}",
        content
    )

    if repeated_sequences:
        issues.append(
            "Text contains unusually long repeated character sequences."
        )

    return issues


def validate_markdown_table(content):
    """
    Checks basic formatting issues in Markdown-style tables.
    LaTeX tables are intentionally excluded.
    Returns warnings rather than assuming the extracted data is incorrect.
    """
    warnings = []

    if not isinstance(content, str) or not content.strip():
        return warnings

    # Do not apply Markdown checks to LaTeX tables.
    if any(marker in content for marker in (
        r"\begin{tabular}",
        r"\begin{longtable}",
        r"\begin{array}"
    )):
        return warnings

    # Identify lines that look like Markdown table rows.
    table_lines = [
        line.strip()
        for line in content.splitlines()
        if "|" in line
    ]

    # Not enough rows to validate a table.
    if len(table_lines) < 2:
        return warnings

    def get_cells(line):
        return [
            cell.strip()
            for cell in line.strip().strip("|").split("|")
        ]

    rows = [get_cells(line) for line in table_lines]

    # Check whether the second row is a Markdown separator.
    separator_pattern = re.compile(r"^:?-{3,}:?$")

    separator_is_valid = (
        len(rows) >= 2
        and all(
            separator_pattern.fullmatch(cell)
            for cell in rows[1]
        )
    )

    if not separator_is_valid:
        warnings.append(
            "Markdown-style table may be missing or have an "
            "invalid header separator row."
        )

    # Check whether all rows have the same number of columns.
    column_counts = [len(row) for row in rows]

    if len(set(column_counts)) > 1:
        warnings.append(
            "Markdown-style table rows have inconsistent column counts."
        )

    # Check for empty column headings.
    if rows and any(not heading for heading in rows[0]):
        warnings.append(
            "Markdown-style table contains an empty header cell."
        )

    return warnings


def validate_heading(content):
    """
    Checks heading content for basic quality issues.
    Returns review findings for suspicious headings.
    """
    issues = []

    if not isinstance(content, str) or not content.strip():
        issues.append("Heading is empty.")
        return issues

    heading = content.strip()

    # Check whether the heading contains at least one letter or digit.
    if not re.search(r"[A-Za-z0-9]", heading):
        issues.append(
            "Heading contains only punctuation or symbols."
        )

    # Flag unusually long headings for manual review.
    if len(heading) > 250:
        issues.append(
            "Heading is unusually long (more than 250 characters)."
        )

    return issues


# ==========================================
# STEP 1: DETECT EXPECTED PDF PAGE COUNT
# ==========================================

def get_expected_page_count(pdf_path):

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(
            f"Input PDF not found: {pdf_path}"
        )

    with pymupdf.open(pdf_path) as document:
        return document.page_count


EXPECTED_PAGE_COUNT = get_expected_page_count(PDF_PATH)

print("Document:", PDF_NAME)
print("Expected page count:", EXPECTED_PAGE_COUNT)


# ==========================================
# STEP 2: STRUCTURAL VALIDATION
# ==========================================

def validate_structure():

    print("\n========== STRUCTURAL VALIDATION ==========")

    os.makedirs(VALIDATED_FOLDER, exist_ok=True)

    page_files = glob.glob(
        os.path.join(
            STRUCTURED_FOLDER,
            "page_*_structured.json"
        )
    )

    # Extract page numbers and sort files
    page_files.sort(
        key=lambda path: int(
            re.search(r"page_(\d+)_structured\.json$", path).group(1)
        )
    )

    available_pages = set()
    page_reports = []

    # --------------------------------------
    # Check each structured page
    # --------------------------------------

    for page_file in page_files:

        filename = os.path.basename(page_file)

        match = re.fullmatch(
            r"page_(\d+)_structured\.json",
            filename
        )

        if not match:
            continue

        page_number = int(match.group(1))
        available_pages.add(page_number)

        issues = []

        try:

            with open(page_file, "r", encoding="utf-8") as file:
                data = json.load(file)

            # Check page mapping
            if data.get("page_number") != page_number:
                issues.append({
                    "type": "PAGE_MAPPING_ERROR",
                    "severity": "REVIEW_REQUIRED",
                    "message": "Page number does not match filename."
                })

            # Check document name
            if data.get("document") != PDF_NAME:
                issues.append({
                    "type": "DOCUMENT_MAPPING_ERROR",
                    "severity": "REVIEW_REQUIRED",
                    "message": "Document name does not match input PDF."
                })

            # Check extracted elements
            elements = data.get("elements")

            if not isinstance(elements, list) or not elements:
                issues.append({
                    "type": "EMPTY_PAGE_CONTENT",
                    "severity": "REVIEW_REQUIRED",
                    "message": "Page has no extracted elements."
                })

            else:

                for index, element in enumerate(elements):

                    # Check element type
                    if not element.get("type"):
                        issues.append({
                            "type": "MISSING_ELEMENT_TYPE",
                            "severity": "REVIEW_REQUIRED",
                            "message": f"Element {index + 1} has no type."
                        })

                    # Check element content
                    if (
                            not isinstance(element.get("content"), str)
                            or not element.get("content", "").strip()
                        ):
                        issues.append({
                            "type": "INVALID_ELEMENT_CONTENT",
                            "severity": "REVIEW_REQUIRED",
                            "message": f"Element {index + 1} has invalid content."
                        })

                    # Check coordinates
                    coordinates = element.get("coordinates")

                    if not isinstance(coordinates, dict):

                        issues.append({
                            "type": "MISSING_COORDINATES",
                            "severity": "REVIEW_REQUIRED",
                            "message": f"Element {index + 1} has no coordinates."
                        })

                    else:

                        coordinate_keys = [
                            "x_start",
                            "y_start",
                            "x_end",
                            "y_end"
                        ]

                        valid_coordinates = True

                        for key in coordinate_keys:

                            value = coordinates.get(key)

                            if (
                                not isinstance(value, (int, float))
                                or isinstance(value, bool)
                                or not __import__("math").isfinite(value)
                            ):
                                valid_coordinates = False
                                break

                        if not valid_coordinates:

                            issues.append({
                                "type": "INVALID_COORDINATES",
                                "severity": "REVIEW_REQUIRED",
                                "message": f"Element {index + 1} has invalid coordinates."
                            })

                        elif (
                            coordinates["x_start"] > coordinates["x_end"]
                            or coordinates["y_start"] > coordinates["y_end"]
                        ):

                            issues.append({
                                "type": "INVALID_COORDINATE_ORDER",
                                "severity": "REVIEW_REQUIRED",
                                "message": f"Element {index + 1} has reversed coordinates."
                            })

            # Check unparsed blocks
            unparsed_blocks = data.get("unparsed_content", [])

            if unparsed_blocks:

                issues.append({
                    "type": "UNPARSED_BLOCKS",
                    "severity": "REVIEW_REQUIRED",
                    "message": f"{len(unparsed_blocks)} unparsed blocks found."
                })

            # Check Nemotron finish reason
            
            metadata = data.get("metadata")

            if not isinstance(metadata, dict):
                metadata = {}

            finish_reason = metadata.get("finish_reason")

            if isinstance(finish_reason, str) and finish_reason.lower() in (
                "length",
                "max_tokens",
                "max_output_tokens"
            ):

                issues.append({
                    "type": "POSSIBLE_TRUNCATION",
                    "severity": "REVIEW_REQUIRED",
                    "message": f"Nemotron response may be truncated. Finish reason: {finish_reason}"
                })

            # Assign page validation status
            if any(
                issue["severity"] == "REVIEW_REQUIRED"
                for issue in issues
            ):
                status = "REVIEW_REQUIRED"

            elif issues:
                status = "WARNING"

            else:
                status = "PASS"

            page_reports.append({
                "document": PDF_NAME,
                "page_number": page_number,
                "validation_status": status,
                "issues": issues
            })

            print(
                f"{status} | Page {page_number} | "
                f"Issues: {len(issues)}"
            )

        except Exception as error:

            page_reports.append({
                "document": PDF_NAME,
                "page_number": page_number,
                "validation_status": "REVIEW_REQUIRED",
                "issues": [{
                    "type": "INVALID_STRUCTURED_FILE",
                    "severity": "REVIEW_REQUIRED",
                    "message": str(error)
                }]
            })

            print(
                f"REVIEW_REQUIRED | Page {page_number} | {error}"
            )

    # --------------------------------------
    # Check missing pages
    # --------------------------------------

    expected_pages = set(range(1, EXPECTED_PAGE_COUNT + 1))

    missing_pages = sorted(expected_pages - available_pages)

    for page_number in missing_pages:

        page_reports.append({
            "document": PDF_NAME,
            "page_number": page_number,
            "validation_status": "REVIEW_REQUIRED",
            "issues": [{
                "type": "MISSING_PAGE",
                "severity": "REVIEW_REQUIRED",
                "message": "Structured output for this page is missing."
            }]
        })

        print(
            f"REVIEW_REQUIRED | Page {page_number} | Missing page."
        )

    # --------------------------------------
    # Generate validation summary
    # --------------------------------------

    pass_count = sum(
        1 for report in page_reports
        if report["validation_status"] == "PASS"
    )

    warning_count = sum(
        1 for report in page_reports
        if report["validation_status"] == "WARNING"
    )

    review_count = sum(
        1 for report in page_reports
        if report["validation_status"] == "REVIEW_REQUIRED"
    )

    summary = {
        "document": PDF_NAME,
        "expected_pages": EXPECTED_PAGE_COUNT,
        "available_page_files": len(available_pages),
        "missing_pages": missing_pages,
        "total_pages_checked": len(page_reports),
        "PASS": pass_count,
        "WARNING": warning_count,
        "REVIEW_REQUIRED": review_count,
        "page_reports": page_reports
    }

    # Save overall validation report
    report_path = os.path.join(
        VALIDATED_FOLDER,
        "structural_validation_report.json"
    )

    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(
            summary,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n========== VALIDATION SUMMARY ==========")
    print("Expected pages:", EXPECTED_PAGE_COUNT)
    print("Available page files:", len(available_pages))
    print("Missing pages:", len(missing_pages))
    print("PASS:", pass_count)
    print("WARNING:", warning_count)
    print("REVIEW_REQUIRED:", review_count)
    print("Report saved:", report_path)
    print("========================================")
    

def validate_content_quality():
    """
    Checks the extracted content for suspicious quality issues.
    This is a conservative heuristic check, not a comparison against
    the original PDF's ground-truth text.
    """

    structured_files = glob.glob(
        os.path.join(STRUCTURED_FOLDER, "page_*_structured.json")
    )

    structured_files.sort(
        key=lambda file: int(
            re.search(r"page_(\d+)_structured\.json", os.path.basename(file)).group(1)
        )
    )

    page_reports = []
    total_pass = 0
    total_warning = 0
    total_review_required = 0


    for file_path in structured_files:
        filename = os.path.basename(file_path)
        match = re.search(r"page_(\d+)_structured\.json", filename)
        page_number = int(match.group(1))

        issues = []
        warnings = []
        review_items = []

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            elements = data.get("elements", [])

            if not isinstance(elements, list):
                review_items.append("The elements field is not a list.")
                elements = []

            # Collect readable content while retaining the original elements.
            page_text_parts = []

            for index, element in enumerate(elements):
                if not isinstance(element, dict):
                    review_items.append(
                        f"Element {index + 1} is not a valid object."
                    )
                    continue

                content = element.get("content", "")
                element_type = str(element.get("type", "")).lower()
                
                
                # Validate section headings.
                if element_type in ("section_header", "heading", "title"):
                    heading_issues = validate_heading(content)

                    for issue in heading_issues:
                        if "unusually long" in issue:
                            warnings.append(
                                f"Element {index + 1}: {issue}"
                            )
                        else:
                            review_items.append(
                                f"Element {index + 1}: {issue}"
                            )


                
                if isinstance(content, str) and content.strip():
                    page_text_parts.append(content)

                    # Detect suspicious extraction patterns.
                    suspicious_issues = check_suspicious_text(content)

                    for issue in suspicious_issues:
                        review_items.append(
                        f"Element {index + 1}: {issue}"
                        )


                    # Check Markdown-style tables only when pipe-delimited
                    # rows are present. LaTeX and other table formats are
                    # left untouched.
                    
                    if element_type == "table":
                        table_warnings = validate_markdown_table(content)

                        for warning in table_warnings:
                            warnings.append(
                                f"Element {index + 1}: {warning}"
                            )


                elif element_type in ("text", "section_header", "table", "chart"):
                    # Structural validation should also identify empty
                    # element content. Keep this as a content-quality finding.
                    warnings.append(
                        f"Element {index + 1}: {element_type} element "
                        "has no readable content."
                    )

            # A page with no readable text may be image-only, so this is
            # a warning rather than an automatic failure.
            if not any(part.strip() for part in page_text_parts):
                warnings.append(
                    "No readable text was extracted from this page. "
                    "Check whether it is an image-only page or content is missing."
                )

            # Check whether the API response indicates possible truncation.
            metadata = data.get("metadata", {})
            if isinstance(metadata, dict):
                finish_reason = str(
                    metadata.get("finish_reason", "")
                ).lower()

                if finish_reason in (
                    "length",
                    "max_tokens",
                    "max_output_tokens"
                ):
                    review_items.append(
                        "The API response may have been truncated because "
                        f"finish_reason is '{finish_reason}'."
                    )

            # Unparsed content needs manual review.
            unparsed_content = data.get("unparsed_content", [])
            if unparsed_content:
                review_items.append(
                    "Unparsed content is present in this page."
                )

            # Assign the page status based on the findings.
            if review_items:
                status = "REVIEW_REQUIRED"
                total_review_required += 1
            elif warnings:
                status = "WARNING"
                total_warning += 1
            else:
                status = "PASS"
                total_pass += 1

            issues = review_items + warnings

            page_reports.append({
                "page_number": page_number,
                "status": status,
                "issues": issues
            })

            print(
                f"{status} | Page {page_number} | "
                f"Issues: {len(issues)}"
            )

        except Exception as error:
            total_review_required += 1

            page_reports.append({
                "page_number": page_number,
                "status": "REVIEW_REQUIRED",
                "issues": [f"Could not validate page: {str(error)}"]
            })

            print(
                f"REVIEW_REQUIRED | Page {page_number} | "
                "Could not read or validate the JSON file."
            )

    report = {
        "document": PDF_NAME,
        "validation_type": "content_quality",
        "expected_pages": EXPECTED_PAGE_COUNT,
        "pages_checked": len(page_reports),
        "summary": {
            "PASS": total_pass,
            "WARNING": total_warning,
            "REVIEW_REQUIRED": total_review_required
        },
        "page_reports": page_reports,
        "note": (
            "These are heuristic checks. PASS does not prove that the "
            "extracted content exactly matches the original PDF. "
            "Review warnings and compare suspicious content with the source."
        )
    }

    os.makedirs(VALIDATED_FOLDER, exist_ok=True)

    report_path = os.path.join(
        VALIDATED_FOLDER,
        "content_validation_report.json"
    )

    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    print("\n========== CONTENT VALIDATION SUMMARY ==========")
    print("Pages checked:", len(page_reports))
    print("PASS:", total_pass)
    print("WARNING:", total_warning)
    print("REVIEW_REQUIRED:", total_review_required)
    print("Report saved:", report_path)
    

def generate_combined_validated_output():
    """
    Combines structural and content-quality validation reports
    into one page-level report for Layer 2.
    """

    structural_report_path = os.path.join(
        VALIDATED_FOLDER,
        "structural_validation_report.json"
    )

    content_report_path = os.path.join(
        VALIDATED_FOLDER,
        "content_validation_report.json"
    )

    # Confirm both reports exist.
    if not os.path.exists(structural_report_path):
        raise FileNotFoundError(
            "Structural validation report not found. "
            "Run structural validation first."
        )

    if not os.path.exists(content_report_path):
        raise FileNotFoundError(
            "Content validation report not found. "
            "Run content validation first."
        )

    # Read both reports.
    with open(structural_report_path, "r", encoding="utf-8") as file:
        structural_report = json.load(file)

    with open(content_report_path, "r", encoding="utf-8") as file:
        content_report = json.load(file)

    # Index page reports by page number.
    structural_pages = {
        page["page_number"]: page
        for page in structural_report.get("page_reports", [])
    }

    content_pages = {
        page["page_number"]: page
        for page in content_report.get("page_reports", [])
    }

    # Include every expected page, even if a report is missing it.
    expected_pages = set(
        range(1, EXPECTED_PAGE_COUNT + 1)
    )

    all_pages = sorted(
        expected_pages
        | set(structural_pages)
        | set(content_pages)
    )

    combined_page_reports = []

    for page_number in all_pages:

        structural_page = structural_pages.get(page_number)
        content_page = content_pages.get(page_number)

        structural_status = (
            structural_page.get("validation_status")
            if structural_page
            else "REVIEW_REQUIRED"
        )

        content_status = (
            content_page.get("status")
            if content_page
            else "REVIEW_REQUIRED"
        )

        structural_issues = (
            structural_page.get("issues", [])
            if structural_page
            else ["Structural validation report is missing for this page."]
        )

        content_issues = (
            content_page.get("issues", [])
            if content_page
            else ["Content validation report is missing for this page."]
        )

        # REVIEW_REQUIRED takes priority over WARNING.
        if (
            structural_status == "REVIEW_REQUIRED"
            or content_status == "REVIEW_REQUIRED"
        ):
            final_status = "REVIEW_REQUIRED"

        elif (
            structural_status == "WARNING"
            or content_status == "WARNING"
        ):
            final_status = "WARNING"

        elif (
            structural_status == "PASS"
            and content_status == "PASS"
        ):
            final_status = "PASS"

        else:
            final_status = "REVIEW_REQUIRED"

        combined_page_reports.append({
            "document": PDF_NAME,
            "page_number": page_number,
            "final_status": final_status,
            "structural_status": structural_status,
            "content_status": content_status,
            "structural_issues": structural_issues,
            "content_issues": content_issues
        })

    # Generate final summary counts.
    pass_count = sum(
        1 for page in combined_page_reports
        if page["final_status"] == "PASS"
    )

    warning_count = sum(
        1 for page in combined_page_reports
        if page["final_status"] == "WARNING"
    )

    review_count = sum(
        1 for page in combined_page_reports
        if page["final_status"] == "REVIEW_REQUIRED"
    )

    combined_report = {
        "document": PDF_NAME,
        "validation_type": "combined",
        "expected_pages": EXPECTED_PAGE_COUNT,
        "total_pages_in_report": len(combined_page_reports),
        "summary": {
            "PASS": pass_count,
            "WARNING": warning_count,
            "REVIEW_REQUIRED": review_count
        },
        "page_reports": combined_page_reports,
        "note": (
            "Final status combines structural and content-quality "
            "validation. REVIEW_REQUIRED pages must be reviewed "
            "before being passed to Layer 2. PASS does not guarantee "
            "perfect extraction accuracy."
        )
    }

    output_path = os.path.join(
        VALIDATED_FOLDER,
        "validated_output.json"
    )

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            combined_report,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n========== COMBINED VALIDATION SUMMARY ==========")
    print("Total pages:", len(combined_page_reports))
    print("PASS:", pass_count)
    print("WARNING:", warning_count)
    print("REVIEW_REQUIRED:", review_count)
    print("Combined report saved:", output_path)
    
    

def generate_layer2_handoff():
    """Prepare validated page content for the Layer 2 pipeline."""

    validation_path = os.path.join(
        VALIDATED_FOLDER,
        "validated_output.json"
    )

    handoff_path = os.path.join(
        VALIDATED_FOLDER,
        "layer2_handoff.json"
    )

    # Read the combined validation report.
    with open(validation_path, "r", encoding="utf-8") as file:
        validation_report = json.load(file)

    ready_pages = []
    excluded_pages = []

    # Process each page using its validation result.
    for page_report in validation_report["page_reports"]:

        page_number = page_report["page_number"]
        final_status = page_report["final_status"]

        # Only PASS pages are eligible for Layer 2.
        if final_status != "PASS":
            excluded_pages.append({
                "page_number": page_number,
                "validation_status": final_status,
                "structural_issues": page_report.get(
                    "structural_issues", []
                ),
                "content_issues": page_report.get(
                    "content_issues", []
                )
            })
            continue

        structured_path = os.path.join(
            STRUCTURED_FOLDER,
            f"page_{page_number}_structured.json"
        )

        # Check that the structured page file exists.
        if not os.path.exists(structured_path):
            excluded_pages.append({
                "page_number": page_number,
                "validation_status": "REVIEW_REQUIRED",
                "reason": "Structured page file is missing."
            })
            continue

        # Read the original extracted page content.
        with open(structured_path, "r", encoding="utf-8") as file:
            structured_page = json.load(file)

        # Confirm that the page mapping is correct.
        if structured_page.get("page_number") != page_number:
            excluded_pages.append({
                "page_number": page_number,
                "validation_status": "REVIEW_REQUIRED",
                "reason": "Page number mismatch in structured file."
            })
            continue

        if structured_page.get("document") != validation_report["document"]:
            excluded_pages.append({
                "page_number": page_number,
                "validation_status": "REVIEW_REQUIRED",
                "reason": "Document name mismatch in structured file."
            })
            continue

        # Preserve the original extracted elements.
        ready_pages.append({
            "page_number": page_number,
            "validation_status": final_status,
            "elements": structured_page.get("elements", [])
        })

    # Build the Layer 2 handoff.
    handoff_status = (
        "READY"
        if not excluded_pages
        and len(ready_pages) == validation_report["expected_pages"]
        else "NOT_READY"
    )

    handoff = {
        "document": validation_report["document"],
        "total_pages": validation_report["expected_pages"],
        "ready_pages": len(ready_pages),
        "excluded_pages": len(excluded_pages),
        "handoff_status": handoff_status,
        "pages": ready_pages,
        "excluded_page_details": excluded_pages,
        "note": (
            "Only pages with PASS validation status and matching "
            "structured page files are included. This handoff "
            "preserves extracted content; PASS does not guarantee "
            "perfect extraction accuracy."
        )
    }

    with open(handoff_path, "w", encoding="utf-8") as file:
        json.dump(
            handoff,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n========== LAYER 2 HANDOFF SUMMARY ==========")
    print("Document:", handoff["document"])
    print("Expected pages:", handoff["total_pages"])
    print("Ready pages:", handoff["ready_pages"])
    print("Excluded pages:", handoff["excluded_pages"])
    print("Handoff status:", handoff_status)
    print("Handoff file saved:", handoff_path)



if __name__ == "__main__":
    validate_structure()
    validate_content_quality()
    generate_combined_validated_output()
    generate_layer2_handoff()