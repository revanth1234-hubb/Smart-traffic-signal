# UrbanTwinAI — Beginner Prototype

This project is a **tabletop demonstration**, not a certified traffic controller. It uses:
- USB webcam + OpenCV + Ultralytics YOLO (`yolo11n.pt`) for frame-visible vehicle detection
- Two camera regions: left half = Lane A, right half = Lane B
- Flask dashboard at `http://127.0.0.1:5000`
- ESP32 over USB serial for two red/yellow/green LED sets
- NetworkX graph with simulated city routes and illustrative ETAs

## 1. Requirements

- Windows 10/11 laptop, Python 3.10 or 3.11 recommended
- USB webcam
- ESP32 development board
- Two sets of red, yellow, green LEDs, or two traffic-light modules
- Six 220–330 ohm resistors if using individual LEDs
- Jumper wires and USB cable

The first model run downloads `yolo11n.pt` from the model provider. Internet is needed for this initial download. The default camera index is 0. If Windows assigns the Zebronics USB camera a different index, set `CAMERA_INDEX` before starting the app.

## 2. Folder structure

```text
UrbanTwinAI/
├── backend/app.py
├── esp32/traffic_lights.ino
├── frontend/index.html
├── frontend/static/style.css
├── frontend/static/script.js
├── requirements.txt
└── README.md
```

## 3. Wiring (individual LEDs)

Use a resistor for **every LED**. GPIO -> resistor -> LED anode (+), LED cathode (-) -> ESP32 GND.

| Lane | LED | ESP32 GPIO |
|---|---|---:|
| A | Red | 16 |
| A | Yellow | 17 |
| A | Green | 18 |
| B | Red | 19 |
| B | Yellow | 21 |
| B | Green | 22 |
| Both | Common LED ground | GND |

The LED ground and ESP32 GND must be connected. Do not connect an LED directly to a GPIO without a resistor. This pinout assumes separate LEDs and an active-HIGH connection. Ready-made traffic-light modules can have different pinouts or active-low inputs; verify their labels/datasheet before wiring. Do not power high-current lamps directly from GPIO pins.

## 4. Install Python packages (Windows)

Open a terminal in the `UrbanTwinAI` folder:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `py -3.11` is unavailable, install Python 3.10 or 3.11 from python.org and create the virtual environment using `python -m venv .venv`.

## 5. Upload ESP32 code

1. Open Arduino IDE.
2. Install the ESP32 board package if not already installed.
3. Select the correct ESP32 board and COM port.
4. Open `esp32/traffic_lights.ino`.
5. Upload it.
6. Close Arduino IDE Serial Monitor before running the Python app; only one program can usually own the COM port at a time.

Test LEDs with the ESP32 USB cable connected. On startup, both lanes are red briefly; the controller then enables a green lane. It only allows one lane green at a time.

## 6. Start the dashboard

Find the ESP32 COM port in Windows Device Manager → Ports (COM & LPT), for example `COM3`.

In PowerShell, from the project folder:

```powershell
$env:SERIAL_PORT="COM3"
$env:CAMERA_INDEX="0"
python backend/app.py
```

If you want to test the dashboard without the ESP32 connected, omit `SERIAL_PORT`:

```powershell
python backend/app.py
```

Open `http://127.0.0.1:5000` in Chrome or Edge. Allow webcam access if Windows asks. The YOLO weights are downloaded on first run. Leave the terminal open while using the dashboard.

## 7. How the demo rules work

- Vehicle classes counted: car, motorcycle, bus, truck.
- Lane A is the **left half** of the camera image; Lane B is the **right half**. Point the camera so the two road lanes align with these regions. If the road is arranged differently, edit the lane split/region logic in `backend/app.py`.
- Low density: 0–2 visible vehicles.
- Medium density: 3–4 visible vehicles.
- High density: 5 or more visible vehicles (configurable using `HEAVY_THRESHOLD`).
- Suggested green duration: `15 + 4 × visible vehicle count`, clamped to 15–40 seconds.
- The ESP32 uses green, yellow, all-red transitions. This is suitable for a low-voltage tabletop demo only.
- Counts are vehicles visible in the current frame, not a cumulative count of unique vehicles passing a checkpoint.

## 8. Troubleshooting

### Camera unavailable
- Close Zoom/Teams/other apps using the camera.
- Try `$env:CAMERA_INDEX="1"` and restart.
- Confirm Windows Camera app can see the webcam.

### `ModuleNotFoundError`
Activate `.venv`, then run `pip install -r requirements.txt` again.

### YOLO model download fails
Check internet access and retry. The initial model download is required unless you already have the weight file available locally. You can set `YOLO_MODEL` to a local compatible model path.

### COM port busy or not found
Close Arduino Serial Monitor. Check Device Manager for the correct COM number and update `$env:SERIAL_PORT`.

### LEDs do not light
Check LED polarity, resistor wiring, shared GND and GPIO pin numbers. If using a ready-made module, verify its input voltage and logic polarity.

### Counts are incorrect
Use a clear, well-lit view; avoid overlapping vehicles; adjust confidence in `model.predict(... conf=0.35 ...)`. The left/right split is only a starter lane assignment. Real deployments need lane polygons and object tracking.

## 9. Current limitations

- Simulated city routes and ETA are not connected to real traffic feeds.
- Route congestion is approximated from the two prototype lane counts.
- This first version uses YOLO detection, not a trained Vision Transformer or GNN.
- Counts are frame-visible detections; they are not unique vehicle counts over time.
- The software does not include pedestrian crossings, emergency-vehicle priority, or certified signal safety logic. Never connect it to public-road traffic lights.

## 10. Staged GNN + Vision Transformer integration

1. **Stage 1 (this prototype):** camera detection, two lane counts, dashboard, serial control, simulated route graph.
2. **Stage 2A (ViT):** extract scene features from a camera frame using a pretrained ViT/Swin model. Validate the visual output against labeled traffic scenes; don't replace detection counts with unvalidated classifications.
3. **Stage 2B (GNN):** define each simulated intersection as a graph node and each road as an edge. Feed observed/simulated speed, flow and congestion into a GNN for short-horizon traffic prediction.
4. **Stage 3 (fusion):** combine ViT visual features with GNN road features and evaluate prediction quality on held-out traffic data.
5. **Stage 4 (optimization):** evaluate signal timing in a traffic simulator such as SUMO before considering real-world deployment.

Useful public datasets to explore later include METR-LA and PeMS traffic datasets. They do not automatically provide labels for your own webcam scene; align training data and evaluation tasks carefully.


## Wi-Fi hotspot connection (ESP32)

1. In `esp32/traffic_lights.ino`, replace `YOUR_HOTSPOT_NAME` and `YOUR_HOTSPOT_PASSWORD` with your phone hotspot credentials.
2. Connect the laptop to the same hotspot. Upload the sketch to the ESP32. Open Serial Monitor at 115200 baud and note the ESP32 IP address. Close Serial Monitor after noting it.
3. In VS Code PowerShell, set the URL printed by the ESP32 (example only):
   ` $env:ESP32_URL="http://192.168.43.100" `
4. Install dependencies with `pip install -r requirements.txt`, then start `python backend/app.py`. Open `http://127.0.0.1:5000`.
5. To test a command directly from PowerShell: `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/signal -ContentType 'application/json' -Body '{"lane":"A","seconds":20}'`.

The ESP32 URL/IP may change when the hotspot reconnects. Check Serial Monitor and update `ESP32_URL` when needed. The dashboard's route/ETA data remains simulated; this prototype is for tabletop demonstration only, not real road signals.
