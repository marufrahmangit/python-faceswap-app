from flask import Flask, render_template, request
import requests
import time
import base64
import os

app = Flask(__name__)

API_KEY = "cmg1vhurc00fhjx04f8okniph"  # your system-generated API key
BASE_URL = "https://prod.api.market/api/v1/magicapi/faceswap-v2/faceswap"

# Ensure static folder exists
if not os.path.exists("static"):
    os.makedirs("static")

@app.route("/", methods=["GET", "POST"])
def index():
    result_url = None
    error_message = None

    # Default URLs for testing
    swap_url = "https://imgur.com/wXDBzHs"
    target_url = "https://imgur.com/UZfuI3E"

    if request.method == "POST":
        # Use form input if provided
        swap_url = request.form.get("swap_url").strip() or swap_url
        target_url = request.form.get("target_url").strip() or target_url

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
                raise Exception("API did not return a request ID.")

            # Step 2: Poll status until completed
            for _ in range(20):  # up to ~60s
                status_url = f"{BASE_URL}/image/status/{request_id}"
                result_response = requests.get(
                    status_url,
                    headers={
                        "accept": "application/json",
                        "x-api-market-key": API_KEY,
                    }
                )
                data = result_response.json()
                print("Polling response:", data)  # debug log

                if data.get("status") == "COMPLETED" and "output" in data:
                    img_base64 = data["output"].split(",")[1]  # remove "data:image/jpeg;base64,"
                    img_bytes = base64.b64decode(img_base64)
                    file_path = "static/result.jpg"
                    with open(file_path, "wb") as f:
                        f.write(img_bytes)
                    result_url = "/static/result.jpg"
                    break
                elif data.get("status") == "FAILED":
                    error_message = "API failed to process the image."
                    break

                time.sleep(3)

            if not result_url and not error_message:
                error_message = "Processing took too long. Try again."

        except Exception as e:
            error_message = f"Error: {str(e)}"

    return render_template("index.html",
                           result_url=result_url,
                           error_message=error_message,
                           swap_url=swap_url,
                           target_url=target_url)

if __name__ == "__main__":
    app.run(debug=True)
