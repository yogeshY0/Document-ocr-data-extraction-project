import os
from google import genai
from google.genai import types
from google.genai.errors import APIError
from qrlib.QRComponent import QRComponent
from app.models.document import ExtractedData
from robot.libraries.BuiltIn import BuiltIn


class ExtractionComponent(QRComponent):

    def __init__(self):
        super().__init__()
        self.client = None

    def setup(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.client = genai.Client(api_key=api_key)

    def extract_document_data(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Local file not found at path: {file_path}")

        remote_file = None
        try:
            remote_file = self.client.files.upload(file=file_path)

            system_instruction = """
            You are an expert document extraction engine. Extract key-value text pairs from the document.

            EXTRACTION & NORMALIZATION RULES:
            1. DATE NORMALIZATION: Convert all dates (date_of_birth, expiry_date) to strictly YYYY-MM-DD format.
            2. WHITESPACE CLEANUP: Strip leading/trailing extra whitespace and newlines from all extracted values.
            3. ABSOLUTE OMISSION RULE: For optional fields (nationality, expiry_date), return null if they do NOT exist.
            4. OCR CONFIDENCE: Return ocr_confidence as a number from 0 to 100.
            """

            self.logger.info("Calling Gemini API with structured response schema...")
            response = self.client.models.generate_content(
                model="gemini-3.5-flash",
                contents=[remote_file, "Extract all key document information standardizing dates."],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ExtractedData,
                    temperature=0.0
                )
            )
            BuiltIn().log(f"Gemini response: {response}", console=True)

            extracted_data: ExtractedData = response.parsed
            result_dict = extracted_data.model_dump()

            clean_dict = {}
            for key, val in result_dict.items():
                if isinstance(val, str):
                    val = val.strip()
                if val is not None:
                    clean_dict[key] = val

            return clean_dict

        except APIError as api_err:
            self.logger.error(f"Gemini API Error during extraction: {api_err}")
            raise
        except Exception as err:
            self.logger.critical(f"Unexpected failure in ExtractionComponent: {err}")
            raise
        finally:
            if remote_file:
                try:
                    self.client.files.delete(name=remote_file.name)
                    self.logger.info(f"Cleaned up remote Gemini file: {remote_file.name}")
                except Exception as cleanup_err:
                    self.logger.warning(f"Failed to delete remote file: {cleanup_err}")