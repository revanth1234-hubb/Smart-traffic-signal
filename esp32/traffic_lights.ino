
#include <WiFi.h>
#include <WebServer.h>

// Your mobile hotspot credentials
const char* ssid = "YOUR_HOTSPOT_NAME";
const char* password = "YOUR_HOTSPOT_PASSWORD";

// Lane A LEDs
const int A_RED = 16;
const int A_YELLOW = 17;
const int A_GREEN = 18;

// Lane B LEDs
const int B_RED = 19;
const int B_YELLOW = 21;
const int B_GREEN = 22;

WebServer server(80);

char activeLane = 'A';
char requestedLane = 'A';

int greenSeconds = 15;

const unsigned long YELLOW_TIME = 3000;
const unsigned long ALL_RED_TIME = 1000;
const unsigned long MIN_GREEN_TIME = 5000;

enum Phase { GREEN, YELLOW, ALL_RED };
Phase phase = ALL_RED;

unsigned long phaseStart = 0;
unsigned long greenStart = 0;

void allRed() {
  digitalWrite(A_RED, HIGH);
  digitalWrite(A_YELLOW, LOW);
  digitalWrite(A_GREEN, LOW);

  digitalWrite(B_RED, HIGH);
  digitalWrite(B_YELLOW, LOW);
  digitalWrite(B_GREEN, LOW);
}

void setGreen(char lane) {
  allRed();

  if (lane == 'A') {
    digitalWrite(A_RED, LOW);
    digitalWrite(A_GREEN, HIGH);
  } else {
    digitalWrite(B_RED, LOW);
    digitalWrite(B_GREEN, HIGH);
  }
}

void setYellow(char lane) {
  allRed();

  if (lane == 'A') {
    digitalWrite(A_RED, LOW);
    digitalWrite(A_YELLOW, HIGH);
  } else {
    digitalWrite(B_RED, LOW);
    digitalWrite(B_YELLOW, HIGH);
  }
}

// Test the ESP32 connection in your browser:
// http://ESP32_IP/status
void handleStatus() {
  String json = "{\"connected\":true,\"ip\":\"";
  json += WiFi.localIP().toString();
  json += "\",\"activeLane\":\"";
  json += activeLane;
  json += "\",\"greenSeconds\":";
  json += String(greenSeconds);
  json += "}";

  server.send(200, "application/json", json);
}

// Python dashboard calls:
// /signal?lane=A&seconds=20
// /signal?lane=B&seconds=25
void handleSignal() {
  if (!server.hasArg("lane") ||
      !server.hasArg("seconds")) {
    server.send(400, "text/plain",
                "Use lane and seconds parameters");
    return;
  }

  String lane = server.arg("lane");
  lane.toUpperCase();

  int seconds = server.arg("seconds").toInt();

  if ((lane != "A" && lane != "B") ||
      seconds < 5 || seconds > 40) {
    server.send(400, "text/plain",
                "Lane must be A/B and seconds 5-40");
    return;
  }

  requestedLane = lane.charAt(0);
  greenSeconds = seconds;

  Serial.printf("Dashboard command: Lane %c, %d seconds\n",
                requestedLane, greenSeconds);

  server.send(200, "application/json",
              "{\"ok\":true,\"message\":\"Command received\"}");
}

void setup() {
  Serial.begin(115200);

  pinMode(A_RED, OUTPUT);
  pinMode(A_YELLOW, OUTPUT);
  pinMode(A_GREEN, OUTPUT);

  pinMode(B_RED, OUTPUT);
  pinMode(B_YELLOW, OUTPUT);
  pinMode(B_GREEN, OUTPUT);

  allRed();

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Connecting to mobile hotspot");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWi-Fi connected!");
  Serial.print("ESP32 IP: http://");
  Serial.println(WiFi.localIP());

  server.on("/", HTTP_GET, []() {
    server.send(200, "text/plain",
                "UrbanTwinAI ESP32 is online");
  });

  server.on("/status", HTTP_GET, handleStatus);
  server.on("/signal", HTTP_GET, handleSignal);
  server.begin();

  Serial.println("Wi-Fi traffic controller ready.");

  phase = ALL_RED;
  phaseStart = millis();
}

void loop() {
  server.handleClient();

  if (WiFi.status() != WL_CONNECTED) {
    allRed();
    delay(100);
    return;
  }

  unsigned long now = millis();

  if (phase == ALL_RED) {
    if (now - phaseStart >= ALL_RED_TIME) {
      activeLane = requestedLane;
      setGreen(activeLane);
      phase = GREEN;
      phaseStart = now;
      greenStart = now;
    }
  }
  else if (phase == GREEN) {
    bool minimumPassed =
        now - greenStart >= MIN_GREEN_TIME;

    bool durationPassed =
        now - greenStart >=
        (unsigned long)greenSeconds * 1000UL;

    bool laneChanged =
        requestedLane != activeLane;

    if (minimumPassed &&
        (durationPassed || laneChanged)) {
      setYellow(activeLane);
      phase = YELLOW;
      phaseStart = now;
    }
  }
  else if (phase == YELLOW) {
    if (now - phaseStart >= YELLOW_TIME) {
      allRed();

      // If Python selected another lane, use it.
      // Otherwise alternate fairly between lanes.
      if (requestedLane != activeLane) {
        activeLane = requestedLane;
      } else {
        activeLane = (activeLane == 'A') ? 'B' : 'A';
      }

      requestedLane = activeLane;

      phase = ALL_RED;
      phaseStart = now;
    }
  }

  delay(2);
}