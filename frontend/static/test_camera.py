
import cv2

# Try the default webcam first
camera = cv2.VideoCapture(0)

# If camera 0 does not work, try camera 1
if not camera.isOpened():
    camera.release()
    camera = cv2.VideoCapture(1)

if not camera.isOpened():
    print("ERROR: Webcam not detected.")
    print("Check the USB connection and camera permissions.")
    raise SystemExit

print("Webcam connected successfully!")
print("Press Q to close the camera window.")

while True:
    success, frame = camera.read()

    if not success:
        print("Could not read webcam video.")
        break

    cv2.imshow("UrbanTwinAI - Zebronics Webcam", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()