from flask import Flask, render_template, request, jsonify, send_from_directory
import requests
import base64
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import mimetypes

load_dotenv()  # take environment variables from .env

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")

# Create necessary folders
folders = ["static", "uploads/source", "uploads/target", "uploads/results"]
for folder in folders:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_url(filepath):
    """Convert local file path to accessible URL"""
    # For local development, return relative path
    # For production, you might need to adjust this based on your hosting setup
    return "/" + filepath.replace("\\", "/")


def upload_file_to_hosting(file, folder):
    """Upload file to the specified folder and return the file path"""
    if file and allowed_file(file.filename):
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        unique_filename = f"{timestamp}_{unique_id}_{name}{ext}"

        filepath = os.path.join(folder, unique_filename)
        file.save(filepath)
        return filepath
    return None


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    directory = os.path.dirname(filename)
    file = os.path.basename(filename)
    return send_from_directory(f'uploads/{directory}', file)


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)


@app.route("/swap", methods=["POST"])
def swap():
    try:
        source_url = None
        target_url = None

        # Handle source image (file or URL)
        if 'source_file' in request.files:
            source_file = request.files['source_file']
            if source_file and source_file.filename:
                source_path = upload_file_to_hosting(source_file, "uploads/source")
                if source_path:
                    # Convert to full URL for the API
                    source_url = request.url_root.rstrip('/') + get_file_url(source_path)
                else:
                    return jsonify({"status": "error",
                                    "message": "Invalid source file format. Please use JPG, PNG, or other supported image formats."})
        else:
            source_url = request.form.get("swap_url", "").strip()

        # Handle target image (file or URL)
        if 'target_file' in request.files:
            target_file = request.files['target_file']
            if target_file and target_file.filename:
                target_path = upload_file_to_hosting(target_file, "uploads/target")
                if target_path:
                    # Convert to full URL for the API
                    target_url = request.url_root.rstrip('/') + get_file_url(target_path)
                else:
                    return jsonify({"status": "error",
                                    "message": "Invalid target file format. Please use JPG, PNG, or other supported image formats."})
        else:
            target_url = request.form.get("target_url", "").strip()

        if not source_url or not target_url:
            return jsonify({"status": "error", "message": "Both source and target images are required."})

        # Validate URLs are accessible
        for url, name in [(source_url, "source"), (target_url, "target")]:
            try:
                response = requests.head(url, timeout=10)
                if response.status_code != 200:
                    return jsonify({"status": "error",
                                    "message": f"Cannot access {name} image. Please check the URL or try uploading the file directly."})

                # Check if it's actually an image
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    return jsonify(
                        {"status": "error", "message": f"The {name} URL does not point to a valid image file."})

            except requests.exceptions.RequestException:
                return jsonify({"status": "error",
                                "message": f"Cannot access {name} image. Please check your internet connection or try a different image."})

        # Step 1: Start face swap with the API
        run_url = f"{BASE_URL}/image/run"
        response = requests.post(
            run_url,
            headers={
                "accept": "application/json",
                "x-api-market-key": API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "input": {
                    "swap_image": source_url,
                    "target_image": target_url,
                }
            },
            timeout=30
        )

        response.raise_for_status()
        data = response.json()
        request_id = data.get("id")

        if not request_id:
            return jsonify({"status": "error", "message": "API did not return a request ID. Please try again."})

        return jsonify({"status": "processing", "request_id": request_id})

    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"API request failed: {str(e)}"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Unexpected error: {str(e)}"})


@app.route("/status/<request_id>")
def status(request_id):
    try:
        status_url = f"{BASE_URL}/image/status/{request_id}"
        result_response = requests.get(
            status_url,
            headers={
                "accept": "application/json",
                "x-api-market-key": API_KEY,
            },
            timeout=30
        )

        result_response.raise_for_status()
        data = result_response.json()

        if data.get("status") == "COMPLETED" and "output" in data:
            try:
                # Parse base64 image data
                output_data = data["output"]
                if "," in output_data:
                    img_base64 = output_data.split(",")[1]
                else:
                    img_base64 = output_data

                img_bytes = base64.b64decode(img_base64)

                # Generate unique filename for result
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_id = str(uuid.uuid4())[:8]
                result_filename = f"faceswap_{timestamp}_{unique_id}.jpg"
                result_path = os.path.join("uploads/results", result_filename)

                # Save the result image
                with open(result_path, "wb") as f:
                    f.write(img_bytes)

                result_url = get_file_url(result_path)
                return jsonify({"status": "completed", "result_url": result_url})

            except Exception as e:
                return jsonify({"status": "error", "message": f"Error processing result image: {str(e)}"})

        elif data.get("status") == "FAILED":
            # Enhanced user-friendly error message
            message = (
                "Face swap failed. Common reasons:\n"
                "• Source image does not clearly show a face\n"
                "• Target image face is too large, small, or angled\n"
                "• Faces are obstructed, blurry, or low quality\n"
                "• Images are too dark or have poor lighting\n\n"
                "Please try with clearer, well-lit face images."
            )
            if "error" in data:
                error_detail = str(data['error'])[:200]  # Limit error length
                message += f"\n\nTechnical details: {error_detail}"
            return jsonify({"status": "failed", "message": message})
        else:
            # Return progress info (simulate % based on API delay/execution time if available)
            delay = data.get("delayTime", 0)
            execution = data.get("executionTime", 0)
            total = delay + execution + 5000  # rough estimate with buffer
            completed = min(delay + execution, total)
            percent = min(int(completed / total * 100) if total else 10, 95)  # Cap at 95% until complete
            return jsonify({"status": "processing", "percent": percent})

    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"Status check failed: {str(e)}"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Unexpected error during status check: {str(e)}"})


@app.route("/download/<path:filename>")
def download_file(filename):
    """Allow downloading of result files"""
    try:
        directory = os.path.dirname(filename)
        file = os.path.basename(filename)
        return send_from_directory(f'uploads/{directory}', file, as_attachment=True)
    except Exception as e:
        return jsonify({"error": "File not found"}), 404


@app.errorhandler(413)
def too_large(e):
    return jsonify({"status": "error", "message": "File too large. Please upload images smaller than 16MB."}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal server error. Please try again."}), 500


if __name__ == "__main__":
    # Create a simple test route to check if folders are created
    @app.route("/test")
    def test():
        folder_status = {}
        for folder in folders:
            folder_status[folder] = os.path.exists(folder)
        return jsonify({
            "folders_created": folder_status,
            "allowed_extensions": list(ALLOWED_EXTENSIONS),
            "max_file_size": "16MB"
        })


    app.run(debug=True, host='0.0.0.0', port=5000)