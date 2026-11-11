
import json
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

# Make the project root available for importing validation.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import validation as validator


class ValidationTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.structured_dir = self.root / "structured"
        self.validated_dir = self.root / "validated"

        self.structured_dir.mkdir()
        self.validated_dir.mkdir()

        # Redirect the existing validator to temporary folders.
        validator.STRUCTURED_FOLDER = str(self.structured_dir)
        validator.VALIDATED_FOLDER = str(self.validated_dir)
        validator.EXPECTED_PAGE_COUNT = 1
        validator.PDF_NAME = "sample.pdf"

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_valid_page(self):
        return {
            "document": "sample.pdf",
            "page_number": 1,
            "elements": [
                {
                    "type": "text",
                    "content": "This is a valid sample sentence.",
                    "coordinates": {
                        "x_start": 0.1,
                        "y_start": 0.1,
                        "x_end": 0.8,
                        "y_end": 0.2
                    }
                }
            ],
            "unparsed_content": [],
            "metadata": {
                "finish_reason": "stop"
            }
        }

    def run_validators(self, data):
        page_path = self.structured_dir / "page_1_structured.json"

        with open(page_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

        # Run both existing validation functions.
        with redirect_stdout(StringIO()):
            validator.validate_structure()
            validator.validate_content_quality()

        with open(
            self.validated_dir / "structural_validation_report.json",
            "r",
            encoding="utf-8"
        ) as file:
            structural_report = json.load(file)

        with open(
            self.validated_dir / "content_validation_report.json",
            "r",
            encoding="utf-8"
        ) as file:
            content_report = json.load(file)

        structural_status = structural_report["page_reports"][0][
            "validation_status"
        ]

        content_status = content_report["page_reports"][0]["status"]

        return structural_status, content_status

    def check_case(
        self,
        data,
        expected_structural,
        expected_content
    ):
        actual_structural, actual_content = self.run_validators(data)

        self.assertEqual(actual_structural, expected_structural)
        self.assertEqual(actual_content, expected_content)

    def test_valid_page(self):
        self.check_case(
            self.create_valid_page(),
            "PASS",
            "PASS"
        )

    def test_empty_page(self):
        data = self.create_valid_page()
        data["elements"] = []

        self.check_case(
            data,
            "REVIEW_REQUIRED",
            "WARNING"
        )

    def test_incorrect_page_mapping(self):
        data = self.create_valid_page()
        data["page_number"] = 2

        self.check_case(
            data,
            "REVIEW_REQUIRED",
            "PASS"
        )

    def test_malformed_markdown_table(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "table",
                "content": "| Name | Age |\n| John | 25 | City |",
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.3
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "WARNING"
        )
        
    
    def test_missing_table_separator(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "table",
                "content": "| Name | Age |\n| John | 25 |",
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.3
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "WARNING"
        )

    def test_empty_table_header(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "table",
                "content": "| | Age |\n|---|---|\n| John | 25 |",
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.3
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "WARNING"
        )

    def test_valid_markdown_table(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "table",
                "content": "| Name | Age |\n|---|---|\n| John | 25 |",
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.3
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "PASS"
        )
        
    
    def test_empty_heading(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "section_header",
                "content": "",
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.2
                }
            }
        ]

        self.check_case(
            data,
            "REVIEW_REQUIRED",
            "REVIEW_REQUIRED"
        )

    def test_heading_only_symbols(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "section_header",
                "content": "!!! ### @@@",
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.2
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "REVIEW_REQUIRED"
        )

    def test_unusually_long_heading(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "section_header",
                "content": "Long heading with several meaningful words describing a topic in detail " * 5,
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.2
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "WARNING"
        )


    def test_latex_table_not_flagged(self):
        data = self.create_valid_page()
        data["elements"] = [
            {
                "type": "table",
                "content": (
                    r"\begin{tabular}{cc}"
                    "\nName & Age \\\\"
                    "\nJohn & 25 \\\\"
                    "\n\\end{tabular}"
                ),
                "coordinates": {
                    "x_start": 0.1,
                    "y_start": 0.1,
                    "x_end": 0.8,
                    "y_end": 0.3
                }
            }
        ]

        self.check_case(
            data,
            "PASS",
            "PASS"
        )


    def test_encoding_replacement_character(self):
        data = self.create_valid_page()
        data["elements"][0]["content"] = "Example text � with encoding issue."

        self.check_case(
            data,
            "PASS",
            "REVIEW_REQUIRED"
        )

    def test_truncated_response(self):
        data = self.create_valid_page()
        data["metadata"]["finish_reason"] = "length"

        self.check_case(
            data,
            "REVIEW_REQUIRED",
            "REVIEW_REQUIRED"
        )

    def test_unparsed_content(self):
        data = self.create_valid_page()
        data["unparsed_content"] = ["Unparsed sample block"]

        self.check_case(
            data,
            "REVIEW_REQUIRED",
            "REVIEW_REQUIRED"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)