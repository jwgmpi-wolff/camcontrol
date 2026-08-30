"""Probe camera at 10.0.0.161:8000 — YI protocol interaction."""
import socket, time, json

ip = "10.0.0.161"
print("Camera ONLINE at", ip)

for attempt in range(3):
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((ip, 8000))
        print(f"Connected attempt {attempt+1}")
        s.settimeout(2)
        data = b""
        for _ in range(15):
            try:
                chunk = s.recv(4096)
                if chunk:
                    data += chunk
                    print("RECEIVED:", repr(chunk[:300]))
            except socket.timeout:
                break
        if data:
            break
        msg = json.dumps({"msg_id": 1, "token": 0}) + "\n"
        s.sendall(msg.encode())
        try:
            resp = s.recv(4096)
            if resp:
                print("PROBE RESP:", repr(resp[:300]))
        except socket.timeout:
            print("no response to probe")
    except Exception as e:
        print("Error:", e)
    finally:
        s.close()
    time.sleep(1)
