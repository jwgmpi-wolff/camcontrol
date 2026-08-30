"""Experimental probe: try multiple YI protocol magic/format variants."""
import socket, struct, time

ip = "10.0.0.248"
port = 8000

def try_variant(name, send_bytes=None, wait_first=0):
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect((ip, port))
        print(f"[{name}] Connected")
        if wait_first:
            time.sleep(wait_first)
        # Listen first
        s.settimeout(2)
        try:
            banner = s.recv(512)
            print(f"[{name}] Camera sent first: {banner.hex()} ({repr(banner[:50])})")
            return banner
        except socket.timeout:
            if send_bytes is None:
                print(f"[{name}] No banner, nothing sent")
                return None
        # Now send
        if send_bytes:
            s.sendall(send_bytes)
            print(f"[{name}] Sent {len(send_bytes)} bytes: {send_bytes.hex()}")
            try:
                resp = s.recv(512)
                print(f"[{name}] Response: {resp.hex()} ({repr(resp[:50])})")
                return resp
            except socket.timeout:
                print(f"[{name}] No response")
            except ConnectionResetError:
                print(f"[{name}] Connection reset after send")
    except ConnectionResetError:
        print(f"[{name}] Connection reset on connect/send")
    except Exception as e:
        print(f"[{name}] Error: {e}")
    finally:
        s.close()
    return None

print("=== YI Protocol Variant Probe ===\n")

# 1. Just connect and wait - see if camera sends anything
try_variant("listen-only", wait_first=2)

# 2. Big-endian magic 0x55AA55AA + token request 1000
pkt_be = struct.pack(">IIII", 0x55AA55AA, 1000, 0, 0)
try_variant("big-endian-magic", pkt_be)

# 3. Little-endian magic
pkt_le = struct.pack("<IIII", 0x55AA55AA, 1000, 0, 0)
try_variant("little-endian-magic", pkt_le)

# 4. No magic, just JSON
pkt_json = b'{"msg_id":1000,"token":0}\n'
try_variant("json-newline", pkt_json)

# 5. Wait 1s before sending
try_variant("wait-then-be", pkt_be, wait_first=1)

# 6. Different magic: 0xAA55AA55
pkt_alt = struct.pack(">IIII", 0xAA55AA55, 1000, 0, 0)
try_variant("alt-magic-AA55", pkt_alt)

# 7. Minimal: just 4 zero bytes
try_variant("zero-4", b"\x00\x00\x00\x00")

# 8. Single null byte
try_variant("single-null", b"\x00")

print("\nDone")
