
import pymupdf
import os
import re
import json
import requests
from dotenv import load_dotenv


# ==========================================
# CONFIGURATION
# ==========================================

PDF_PATH = "samples/sample.pdf"
IMAGE_FOLDER = "outputs/images"
OUTPUT_FOLDER = "outputs"

API_URL = (
    "https://ai.api.nvidia.com/v1/retrieval/"
    "nvidia/nemotron-3.5-parse/parse"
)

# Initially process only 10 new pages per run.
# Later, change this to None to process all remaining pages.
MAX_PAGES_PER_RUN = None

MAX_OUTPUT_TOKENS = 4096


# ==========================================
# STEP 1: PDF TO IMAGE CONVERSION
# ==========================================

def convert_pdf_to_images(pdf_path):

    document = pymupdf.open(pdf_path)

    os.makedirs(IMAGE_FOLDER, exist_ok=True)

    for page_number, page in enumerate(document, start=1):

        image_path = f"{IMAGE_FOLDER}/page_{page_number}.png"

        # Skip images that already exist
        if os.path.exists(image_path):
            continue

        pix = page.get_pixmap(
            dpi=300,
            colorspace=pymupdf.csRGB,
            alpha=False
        )

        pix.save(image_path)

        print(f"Page {page_number} converted: {image_path}")

    document.close()

    print("PDF conversion completed!")


# ==========================================
# STEP 2: NVIDIA API CONFIGURATION
# ==========================================

load_dotenv()

API_KEY = os.getenv("NVIDIA_API_KEY")


# ==========================================
# STEP 3: SEND ONE IMAGE TO NEMOTRON
# ==========================================

def parse_image(image_path):

    if not API_KEY:
        raise ValueError("NVIDIA API key not found!")

    # Extract page number from image filename
    filename = os.path.basename(image_path)

    match = re.fullmatch(r"page_(\d+)\.png", filename)

    if not match:
        raise ValueError(f"Unexpected image filename: {filename}")

    page_number = int(match.group(1))

    output_path = f"{OUTPUT_FOLDER}/page_{page_number}.json"

    # Skip pages that already have a valid response
    if os.path.exists(output_path):

        try:
            with open(output_path, "r", encoding="utf-8") as file:
                existing_result = json.load(file)

            if existing_result.get("content"):
                print(f"Skipping page {page_number}: response already exists.")
                return True

        except (json.JSONDecodeError, OSError):
            print(f"Existing response for page {page_number} is invalid. Retrying.")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }

    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    files = {
        "document": (
            filename,
            image_bytes,
            "image/png"
        ),
        "options": (
            None,
            json.dumps({
                "decoding": {
                    "max_output_tokens": MAX_OUTPUT_TOKENS
                }
            }),
            "application/json"
        )
    }

    print(f"\nSending page {page_number} to Nemotron...")

    response = requests.post(
        API_URL,
        headers=headers,
        files=files,
        timeout=360
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("content"):
        raise ValueError("Nemotron returned an empty content response.")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(f"Page {page_number} parsed successfully!")
    print("Finish reason:", result.get("finish_reason"))
    print("Usage:", result.get("usage"))
    print("Saved response:", output_path)

    print("\nExtracted content preview:")
    print(result.get("content", "")[:500])

    return True


# ==========================================
# STEP 4: PROCESS MULTIPLE PAGE IMAGES
# ==========================================

def process_all_images():

    if not API_KEY:
        raise ValueError("NVIDIA API key not found!")

    if not os.path.isdir(IMAGE_FOLDER):
        raise FileNotFoundError(
            f"Image folder not found: {IMAGE_FOLDER}"
        )

    image_files = [
        filename
        for filename in os.listdir(IMAGE_FOLDER)
        if re.fullmatch(r"page_\d+\.png", filename)
    ]

    image_files.sort(
        key=lambda filename: int(
            re.search(r"page_(\d+)", filename).group(1)
        )
    )

    if not image_files:
        print("No page images found!")
        return

    print(f"\nTotal page images found: {len(image_files)}")

    successful_pages = 0
    failed_pages = 0
    processed_this_run = 0

    for filename in image_files:

        if (
            MAX_PAGES_PER_RUN is not None
            and processed_this_run >= MAX_PAGES_PER_RUN
        ):
            break

        image_path = os.path.join(IMAGE_FOLDER, filename)

        page_number = int(
            re.search(r"page_(\d+)", filename).group(1)
        )

        output_path = f"{OUTPUT_FOLDER}/page_{page_number}.json"

        # Existing valid responses do not count towards this batch
        if os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as file:
                    existing_result = json.load(file)

                if existing_result.get("content"):
                    print(f"Page {page_number}: already completed.")
                    continue

            except (json.JSONDecodeError, OSError):
                pass

        processed_this_run += 1

        try:
            parse_image(image_path)
            successful_pages += 1

        except requests.RequestException as error:
            failed_pages += 1
            print(f"API error on page {page_number}: {error}")

        except Exception as error:
            failed_pages += 1
            print(f"Error on page {page_number}: {error}")

    print("\n========== API PROCESSING SUMMARY ==========")
    print("Page images available:", len(image_files))
    print("New pages attempted:", processed_this_run)
    print("Successful pages:", successful_pages)
    print("Failed pages:", failed_pages)
    print("Raw JSON folder:", OUTPUT_FOLDER)
    print("============================================")


# ==========================================
# MAIN EXECUTION
# ==========================================

if __name__ == "__main__":

    # Uncomment this line only if PDF images need to be generated.
    convert_pdf_to_images(PDF_PATH)

    # Process new page images through Nemotron.
    process_all_images()
