"""Generate qr-connect.png — run once to refresh the connect QR code image."""
import json
import os
import socket

import qrcode


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.0.0.1", 1))
        return s.getsockname()[0]
    finally:
        s.close()


ip = _local_ip()
payload = json.dumps(
    {
        "gateway": f"http://{ip}:8080",
        "camera": "10.0.0.161",
        "cameraPort": 8000,
        "model": "YI-YHS3017",
        "rtsp": "rtsp://10.0.0.161/ch0_0.h264",
    }
)
print("Payload:", payload)

qr = qrcode.QRCode(
    error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4
)
qr.add_data(payload)
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
out = os.path.join(os.path.dirname(__file__), "qr-connect.png")
img.save(out)
print("Saved:", out)
print("Size:", img.size)
