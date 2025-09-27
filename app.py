from flask import Flask, render_template, request, jsonify
import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")

# Ensure static folder exists
if not os.path.exists("static"):
    os.makedirs("static")


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")


@app.route("/swap", methods=["POST"])
def swap():
    swap_url = request.form.get("swap_url", "").strip()
    target_url = request.form.get("target_url", "").strip()

    if not swap_url or not target_url:
        return jsonify({"status": "error", "message": "Both image URLs are required."})

    try:
        # Step 1: Start face swap
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
                    "swap_image": swap_url,
                    "target_image": target_url,
                }
            }
        )
        response.raise_for_status()
        request_id = response.json().get("id")
        if not request_id:
            return jsonify({"status": "error", "message": "API did not return a request ID."})

        return jsonify({"status": "processing", "request_id": request_id})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/status/<request_id>")
def status(request_id):
    try:
        status_url = f"{BASE_URL}/image/status/{request_id}"
        result_response = requests.get(
            status_url,
            headers={
                "accept": "application/json",
                "x-api-market-key": API_KEY,
            }
        )
        data = result_response.json()

        if data.get("status") == "COMPLETED" and "output" in data:
            img_base64 = data["output"].split(",")[1]
            img_bytes = base64.b64decode(img_base64)
            file_path = "static/result.jpg"
            with open(file_path, "wb") as f:
                f.write(img_bytes)
            return jsonify({"status": "completed", "result_url": "/static/result.jpg"})
        elif data.get("status") == "FAILED":
            # Enhanced user-friendly error message
            message = (
                "Face swap failed. Common reasons:\n"
                "- Source image does not clearly show a face.\n"
                "- Target image face is too large, small, or angled.\n"
                "- Faces are obstructed or blurry.\n"
                "Please try another image."
            )
            if "error" in data:
                message += f"\nAPI error details: {data['error']}"
            return jsonify({"status": "failed", "message": message})
        else:
            # Return progress info (simulate % based on API delay/execution time if available)
            delay = data.get("delayTime", 0)
            execution = data.get("executionTime", 0)
            total = delay + execution + 1000  # rough estimate
            completed = min(delay + execution, total)
            percent = int(completed / total * 100) if total else 0
            return jsonify({"status": "processing", "percent": percent})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


if __name__ == "__main__":
    app.run(debug=True)
