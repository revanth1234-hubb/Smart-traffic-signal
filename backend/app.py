import os
import time
import threading
from collections import deque

import cv2
import networkx as nx
from flask import Flask, Response, jsonify, render_template, request
from ultralytics import YOLO
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, template_folder=os.path.join(ROOT, "frontend"),
            static_folder=os.path.join(ROOT, "frontend", "static"), static_url_path="/static")
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
ESP32_URL = os.getenv("ESP32_URL", "").strip().rstrip("/")
HEAVY_THRESHOLD = int(os.getenv("HEAVY_THRESHOLD", "5"))
MODEL_NAME = os.getenv("YOLO_MODEL", "yolo11n.pt")
ENABLE_CAMERA = os.getenv("ENABLE_CAMERA", "1") != "0"
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

LOCK = threading.Lock()
SIGNAL_LOCK = threading.Lock()
STATE = {
    "camera_status": "Starting", "last_update": time.time(), "vehicles_total": 0,
    "lane_a_count": 0, "lane_b_count": 0, "lane_a_density": "LOW", "lane_b_density": "LOW",
    "congestion": "LOW", "signal_lane": "A", "green_seconds": 15, "route": {}, "routes": [],
    "esp32_status": "Not configured", "fps": 0, "error": ""
}
latest_jpeg = None
last_wifi_command = ""
fps_samples = deque(maxlen=20)


def density(count):
    if count >= HEAVY_THRESHOLD:
        return "HIGH"
    if count >= 3:
        return "MEDIUM"
    return "LOW"


def make_road_graph():
    graph = nx.DiGraph()
    graph.add_edge("START", "CENTRAL", name="Main Avenue", base=4.0, lane="A")
    graph.add_edge("CENTRAL", "DEST", name="Central Link", base=5.0, lane="A")
    graph.add_edge("START", "RIVERSIDE", name="Riverside Road", base=5.0, lane="B")
    graph.add_edge("RIVERSIDE", "DEST", name="Market Link", base=4.0, lane="B")
    graph.add_edge("START", "PARK", name="Park Connector", base=3.8, lane="B")
    graph.add_edge("PARK", "DEST", name="Park Link", base=6.5, lane="B")
    return graph


ROAD_GRAPH = make_road_graph()


def get_routes(count_a, count_b):
    graph = ROAD_GRAPH.copy()
    for _, _, edge in graph.edges(data=True):
        count = count_a if edge["lane"] == "A" else count_b
        edge["weight"] = edge["base"] * (1.0 + min(count, 12) * 0.12)
    try:
        paths = list(nx.shortest_simple_paths(graph, "START", "DEST", weight="weight"))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    routes = []
    for index, path in enumerate(paths[:3]):
        segments, total = [], 0.0
        for u, v in zip(path, path[1:]):
            edge = graph[u][v]
            total += edge["weight"]
            segments.append(edge["name"])
        routes.append({"rank": index + 1, "name": " → ".join(segments),
                       "eta_minutes": round(total, 1), "recommended": index == 0, "nodes": path})
    return routes


def choose_signal(count_a, count_b):
    if count_a > count_b:
        lane, count = "A", count_a
    elif count_b > count_a:
        lane, count = "B", count_b
    else:
        lane = STATE["signal_lane"] if STATE["signal_lane"] in ("A", "B") else "A"
        count = count_a if lane == "A" else count_b
    seconds = max(15, min(40, 15 + count * 4))
    return lane, seconds


def check_esp32():
    if not ESP32_URL:
        with LOCK:
            STATE["esp32_status"] = "Not configured (set ESP32_URL)"
        return
    try:
        response = requests.get(f"{ESP32_URL}/status", timeout=2)
        response.raise_for_status()
        details = response.json()
        with LOCK:
            STATE["esp32_status"] = f"Wi-Fi connected: {details.get('ip', ESP32_URL)}"
    except Exception as exc:
        with LOCK:
            STATE["esp32_status"] = f"Wi-Fi unavailable: {exc}"


def send_signal_command(lane, seconds, force=False):
    global last_wifi_command
    command = f"{lane},{seconds}"
    if not ESP32_URL:
        return
    if command == last_wifi_command and not force:
        return
    try:
        with SIGNAL_LOCK:
            response = requests.get(
                f"{ESP32_URL}/signal",
                params={"lane": lane, "seconds": int(seconds)},
                timeout=2,
            )
            response.raise_for_status()
        last_wifi_command = command
        with LOCK:
            STATE["esp32_status"] = f"Wi-Fi connected (sent Lane {lane}, {seconds}s)"
    except Exception as exc:
        with LOCK:
            STATE["esp32_status"] = f"Wi-Fi command failed: {exc}"


def update_counts(count_a, count_b):
    routes = get_routes(count_a, count_b)
    lane, seconds = choose_signal(count_a, count_b)
    with LOCK:
        STATE.update({
            "last_update": time.time(), "vehicles_total": count_a + count_b,
            "lane_a_count": count_a, "lane_b_count": count_b,
            "lane_a_density": density(count_a), "lane_b_density": density(count_b),
            "congestion": "HIGH" if max(count_a, count_b) >= HEAVY_THRESHOLD else
                          ("MEDIUM" if max(count_a, count_b) >= 3 else "LOW"),
            "signal_lane": lane, "green_seconds": seconds, "routes": routes,
            "route": routes[0] if routes else {}, "error": ""
        })
    send_signal_command(lane, seconds)


def camera_worker():
    global latest_jpeg
    model = None
    while True:
        cap = cv2.VideoCapture(CAMERA_INDEX)
        graph = None
        frame_ready = threading.Event()
        frame_lock = threading.Lock()
        frame_buffer = [None]

        def store_frame(frame):
            with frame_lock:
                frame_buffer[0] = frame
            frame_ready.set()

        def read_graph_frame(timeout=2):
            frame_ready.clear()
            if not graph.grab_frame() or not frame_ready.wait(timeout):
                return None
            with frame_lock:
                return frame_buffer[0].copy()

        ok, frame = cap.read() if cap.isOpened() else (False, None)
        if not ok:
            cap.release()
            try:
                from pygrabber.dshow_graph import FilterGraph

                graph = FilterGraph()
                graph.add_video_input_device(CAMERA_INDEX)
                graph.add_sample_grabber(store_frame)
                graph.add_null_render()
                graph.prepare_preview_graph()
                graph.run()
                frame = read_graph_frame(timeout=5)
                if frame is None:
                    raise RuntimeError("DirectShow did not return a video frame")
            except Exception as exc:
                if graph is not None:
                    try:
                        graph.stop()
                    except Exception:
                        pass
                latest_jpeg = None
                with LOCK:
                    STATE["camera_status"] = f"Camera unavailable (index {CAMERA_INDEX})"
                    STATE["error"] = f"Could not read camera through OpenCV or DirectShow: {exc}"
                time.sleep(2)
                continue
        with LOCK:
            STATE["camera_status"] = "Live"
            STATE["error"] = ""
        while True:
            started = time.time()
            if graph is not None:
                frame = read_graph_frame()
                ok = frame is not None
            else:
                ok, frame = cap.read()
            if not ok:
                latest_jpeg = None
                with LOCK:
                    STATE["camera_status"] = "Camera read failed"
                    STATE["error"] = "Waiting for camera frames. Check its USB connection."
                time.sleep(2)
                break
            if model is None:
                try:
                    model = YOLO(MODEL_NAME)
                except Exception as exc:
                    with LOCK:
                        STATE["camera_status"] = "Model load failed"
                        STATE["error"] = f"Could not load {MODEL_NAME}: {exc}"
                    if graph is not None:
                        graph.stop()
                    cap.release()
                    return
            height, width = frame.shape[:2]
            split_x = width // 2
            count_a = count_b = 0
            try:
                result = model.predict(frame, imgsz=640, conf=0.35, verbose=False)[0]
                if result.boxes is not None:
                    for box in result.boxes:
                        cls_id = int(box.cls[0].item())
                        if cls_id not in VEHICLE_CLASSES:
                            continue
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        cx = (x1 + x2) // 2
                        if cx < split_x:
                            count_a += 1
                            lane_label, color = "Lane A", (0, 220, 80)
                        else:
                            count_b += 1
                            lane_label, color = "Lane B", (0, 180, 255)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame, f"{VEHICLE_CLASSES[cls_id]} | {lane_label}",
                                    (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            except Exception as exc:
                with LOCK:
                    STATE["error"] = f"Detection error: {exc}"
            cv2.line(frame, (split_x, 0), (split_x, height), (255, 255, 0), 2)
            cv2.putText(frame, f"LANE A: {count_a}", (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 80), 2)
            cv2.putText(frame, f"LANE B: {count_b}", (split_x + 15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2)
            cv2.putText(frame, "DEMO: left half = Lane A, right half = Lane B", (15, height - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)
            update_counts(count_a, count_b)
            elapsed = max(time.time() - started, 0.001)
            fps_samples.append(1.0 / elapsed)
            with LOCK:
                STATE["fps"] = round(sum(fps_samples) / len(fps_samples), 1)
            encoded_ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if encoded_ok:
                latest_jpeg = encoded.tobytes()
            time.sleep(0.02)
        if graph is not None:
            graph.stop()
        cap.release()


def gen_video():
    while True:
        frame = latest_jpeg
        if frame is not None:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.05)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    return Response(gen_video(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/state")
def api_state():
    with LOCK:
        snapshot = dict(STATE)
    snapshot["updated_at"] = time.strftime("%H:%M:%S", time.localtime(snapshot["last_update"]))
    return jsonify(snapshot)


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "mode": "wifi" if ESP32_URL else "dashboard-only", "heavy_threshold": HEAVY_THRESHOLD})


@app.route("/api/signal", methods=["POST"])
def api_signal():
    """Send a manual test signal command from the dashboard or API client."""
    data = request.get_json(silent=True) or {}
    lane = str(data.get("lane", "A")).upper()
    try:
        seconds = int(data.get("seconds", 15))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "seconds must be an integer"}), 400
    if lane not in ("A", "B") or not 5 <= seconds <= 40:
        return jsonify({"ok": False, "error": "lane must be A/B and seconds must be 5-40"}), 400
    if not ESP32_URL:
        return jsonify({"ok": False, "error": "Set ESP32_URL before starting Flask"}), 503
    send_signal_command(lane, seconds, force=True)
    with LOCK:
        status = STATE["esp32_status"]
    ok = "command failed" not in status.lower() and "unavailable" not in status.lower()
    return jsonify({"ok": ok, "lane": lane, "seconds": seconds, "esp32_status": status}), (200 if ok else 502)


def main():
    check_esp32()
    if ENABLE_CAMERA:
        threading.Thread(target=camera_worker, daemon=True).start()
    else:
        with LOCK:
            STATE["camera_status"] = "Camera disabled"
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
