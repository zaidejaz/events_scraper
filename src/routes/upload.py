from flask import Blueprint, jsonify, render_template, request, current_app
import os
import pandas as pd
from flask_login import login_required
from ..services import UploadService

bp = Blueprint('upload', __name__)

def get_upload_service():
    return UploadService(
        current_app.config['STORE_API_BASE_URL'],
        current_app.config['STORE_API_KEY'],
        current_app.config['COMPANY_ID']
    )

def process_file_to_utf8(file_path: str) -> str:
    """Process file to UTF-8 CSV regardless of input format."""
    try:
        if file_path.endswith(('.xlsx', '.xls')):
            # Read Excel file
            df = pd.read_excel(file_path)
        else:
            # Try reading CSV with different encodings
            encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
            df = None
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
                    
            if df is None:
                raise ValueError("Could not read file with any supported encoding")

        # Save as UTF-8 CSV
        utf8_path = f"{os.path.splitext(file_path)[0]}_utf8.csv"
        df.to_csv(utf8_path, index=False, encoding='utf-8')
        return utf8_path
    except Exception as e:
        raise ValueError(f"Error processing file: {str(e)}")

@bp.route('/upload')
@login_required
def upload_page():
    return render_template('upload.html')

@bp.route('/api/upload', methods=['POST'])
@login_required
def manual_upload():
    temp_path = None
    try:
        if 'file' not in request.files:
            return jsonify({
                "status": "error",
                "message": "No file provided"
            }), 400

        file = request.files['file']
        if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
            return jsonify({
                "status": "error",
                "message": "Invalid file format"
            }), 400

        # Save file temporarily
        temp_path = os.path.join(current_app.config['OUTPUT_FILE_DIR'], file.filename)
        file.save(temp_path)

        # Upload file
        upload_service = get_upload_service()
        success, message = upload_service.upload_csv(temp_path)

        if success:
            return jsonify({
                "status": "success",
                "message": message
            })
        else:
            return jsonify({
                "status": "error",
                "message": message
            }), 400

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass