import requests
import logging
from typing import Dict, Optional, Tuple
import os
import pandas as pd
import chardet

logger = logging.getLogger(__name__)

class UploadService:
    def __init__(self, api_base_url: str, api_key: str, company_id: str):
        self.api_base_url = api_base_url
        self.headers = {
            'X-Api-Token': api_key,
            'X-Company-Id': company_id,
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.required_headers = [
            'inventory_id', 'event_name', 'venue_name', 'event_date', 
            'event_id', 'quantity', 'section', 'row', 'seats', 'barcodes',
            'internal_notes', 'public_notes', 'tags', 'list_price', 
            'face_price', 'taxed_cost', 'cost', 'hide_seats', 'in_hand',
            'in_hand_date', 'instant_transfer', 'files_available', 
            'split_type', 'custom_split', 'stock_type', 'zone', 
            'shown_quantity', 'passthrough'
        ]

    def create_empty_dataframe(self) -> pd.DataFrame:
        """Create an empty DataFrame with required headers."""
        return pd.DataFrame(columns=self.required_headers)

    def request_upload(self) -> Tuple[bool, Dict]:
        """Request upload credentials from the API."""
        try:
            response = requests.post(
                f"{self.api_base_url}/sync/api/inventories/csv_upload_request",
                headers=self.headers
            )
            response.raise_for_status()
            return True, response.json()
        except Exception as e:
            logger.error(f"Error requesting upload: {str(e)}")
            return False, {"error": str(e)}

    def detect_file_encoding(self, file_path: str) -> Tuple[bool, str]:
        """Detect the encoding of a file."""
        try:
            with open(file_path, 'rb') as file:
                raw_data = file.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding']
                confidence = result['confidence']
                
                logger.info(f"Detected encoding: {encoding} with confidence: {confidence}")
                return True, f"Encoding: {encoding} (confidence: {confidence})"
        except Exception as e:
            return False, f"Error detecting encoding: {str(e)}"

    def verify_utf8_encoding(self, file_path: str) -> Tuple[bool, str]:
        """Verify if file is UTF-8 encoded."""
        try:
            with open(file_path, 'rb') as file:
                content = file.read()
                # Try to decode as UTF-8
                content.decode('utf-8')
                return True, "File is UTF-8 encoded"
        except UnicodeDecodeError as e:
            return False, f"File is not UTF-8 encoded: {str(e)}"
        except Exception as e:
            return False, f"Error checking encoding: {str(e)}"

    def convert_excel_to_csv(self, file_path: str) -> Tuple[bool, str]:
        """Convert Excel file to UTF-8 CSV."""
        try:
            # Create temp CSV file path
            csv_path = f"{os.path.splitext(file_path)[0]}_utf8.csv"
            
            # Read Excel file
            df = pd.read_excel(file_path)
            
            # Save as UTF-8 CSV with BOM
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
            # Verify the encoding
            is_utf8, msg = self.verify_utf8_encoding(csv_path)
            if not is_utf8:
                return False, msg
                
            return True, csv_path
        except Exception as e:
            error_msg = f"Error converting Excel to CSV: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def upload_to_s3(self, file_path: str, upload_data: Dict) -> Tuple[bool, str]:
        """Upload file to S3 using provided credentials."""
        processed_path = None
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"

            # Process file
            df = None
            try:
                if file_path.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file_path)
                else:
                    # Try different encodings for CSV
                    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
                    for encoding in encodings:
                        try:
                            df = pd.read_csv(file_path, encoding=encoding)
                            break
                        except UnicodeDecodeError:
                            continue
            except pd.errors.EmptyDataError:
                # If file is empty, create DataFrame with headers
                df = self.create_empty_dataframe()
            except Exception as e:
                return False, f"Error reading file: {str(e)}"

            if df is None:
                df = self.create_empty_dataframe()

            # Ensure all required columns exist
            for header in self.required_headers:
                if header not in df.columns:
                    df[header] = ""

            # Save as UTF-8 CSV without BOM
            processed_path = f"{os.path.splitext(file_path)[0]}_processed.csv"
            df.to_csv(processed_path, index=False, encoding='utf-8')

            # Extract fields from upload data
            fields = upload_data['upload']['fields']
            url = upload_data['upload']['url']

            # Create form data
            form = {
                'key': fields['key'],
                'Policy': fields['Policy'],
                'X-Amz-Algorithm': fields['X-Amz-Algorithm'],
                'X-Amz-Credential': fields['X-Amz-Credential'],
                'X-Amz-Date': fields['X-Amz-Date'],
                'X-Amz-Signature': fields['X-Amz-Signature']
            }

            # Upload file
            with open(processed_path, 'rb') as f:
                files = {
                    'file': (fields['key'], f, 'text/csv')
                }
                
                response = requests.post(url, data=form, files=files)
                
                if response.status_code not in [200, 201, 204]:
                    logger.error(f"Upload failed: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return False, f"Upload failed with status {response.status_code}"

            return True, "Upload successful"

        except Exception as e:
            error_msg = f"Error uploading to S3: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        finally:
            if processed_path and os.path.exists(processed_path):
                try:
                    os.remove(processed_path)
                except Exception as e:
                    logger.error(f"Error removing temporary file: {str(e)}")

    def upload_csv(self, file_path: str) -> Tuple[bool, str]:
        """Complete upload process including requesting credentials and uploading."""
        # Request upload credentials
        success, upload_data = self.request_upload()
        if not success:
            return False, upload_data.get("error", "Failed to get upload credentials")

        # Upload to S3
        return self.upload_to_s3(file_path, upload_data)