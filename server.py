import os
import time
import threading

from flask import Flask, request, Response, abort, jsonify

app = Flask(__name__)

CAMERA_KEY = os.environ.get("CAMERA_KEY", "")

latest_frame = None
last_update = 0
frame_lock = threading.Lock()


def authorized():
    return (
        CAMERA_KEY
        and request.headers.get("X-API-Key") == CAMERA_KEY
    )


@app.route("/")
def home():
    return """
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>ESP32-CAM</title>
    </head>
    <body style="text-align:center;font-family:Arial">
      <h2>ESP32-CAM Remote Camera</h2>
      <p>Live video and snapshot</p>
      <img src="/stream" style="width:100%;max-width:640px">
      <p><a href="/snapshot">Capture / View Photo</a></p>
    </body>
    </html>
    """


@app.route("/upload", methods=["POST"])
def upload():
    global latest_frame, last_update

    if not authorized():
        abort(401)

    frame = request.get_data()

    if not frame or len(frame) > 500_000:
        abort(400)

    if not frame.startswith(b"\xff\xd8"):
        abort(400)

    with frame_lock:
        latest_frame = frame
        last_update = time.time()

    return jsonify({"ok": True})


def get_frame():
    with frame_lock:
        return latest_frame, last_update


@app.route("/stream")
def stream():
    key = request.args.get("key", "")

    if not CAMERA_KEY or key != CAMERA_KEY:
        abort(401)

    def generate():
        previous_update = 0

        while True:
            frame, updated = get_frame()

            if frame is not None and updated != previous_update:
                previous_update = updated

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                    + frame
                    + b"\r\n"
                )

            else:
                time.sleep(0.03)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"}
    )


@app.route("/snapshot")
def snapshot():
    key = request.args.get("key", "")

    if not CAMERA_KEY or key != CAMERA_KEY:
        abort(401)

    frame, updated = get_frame()

    if frame is None:
        return "No photo received yet", 503

    return Response(
        frame,
        mimetype="image/jpeg",
        headers={"Cache-Control": "no-store"}
    )


@app.route("/health")
def health():
    return jsonify({"status": "running"})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
