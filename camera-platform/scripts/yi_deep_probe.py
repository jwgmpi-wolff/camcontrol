"""Deep YI protocol probe — try many formats to find what the camera responds to."""
import socket, struct, time

ip = "10.0.0.161"


def try_format(name, data, delay=0.0):
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect((ip, 8000))
        if delay:
            time.sleep(delay)
        s.sendall(data)
        s.settimeout(2)
        resp = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
        except socket.timeout:
            pass
        if resp:
            print(f"[{name}] RESPONSE: {resp.hex()} ({len(resp)} bytes)")
            return resp
        print(f"[{name}] No response")
        return None
    except ConnectionResetError:
        print(f"[{name}] Reset")
    except Exception as e:
        print(f"[{name}] Error: {e}")
    finally:
        s.close()


print("=== Deep YI Protocol Probe ===\n")

# Little-endian magic variants
for magic in [0x55AA55AA, 0xAA55AA55, 0x00000001, 0x01000000, 0xFFFFFFFF]:
    for msg_id in [1000, 1, 100, 0xEA03, 0x03EA]:
        pkt = struct.pack("<IIII", magic, msg_id, 0, 0)
        r = try_format(f"le-{magic:08x}-{msg_id}", pkt)
        if r:
            print("!!! FOUND WORKING FORMAT !!!")
            break

# JSON payloads
payloads = [
    b'{"msg_id":1000,"token":0}',
    b'{"msg_id":1000,"token":0}\n',
    b'{"type":"login","params":{"username":"admin","password":""}}',
    b'DMAP',
]
for p in payloads:
    try_format(f"payload-{p[:15]}", p)

# Wait longer variants
pkt_std = struct.pack(">IIII", 0x55AA55AA, 1000, 0, 0)
try_format("wait-0.5s", pkt_std, delay=0.5)
try_format("wait-1s", pkt_std, delay=1.0)

print("\nDone")
