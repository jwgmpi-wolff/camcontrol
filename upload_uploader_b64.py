#!/usr/bin/env python3
"""Upload uploader binary via piped cat command."""

import paramiko
import base64
from pathlib import Path

uploader_file = Path('src/camera_bridge/oncam/camcontrol-uploader')
if not uploader_file.exists():
    print(f'ERROR: Uploader binary not found at {uploader_file}')
    exit(1)

binary_data = uploader_file.read_bytes()
print(f'Binary size: {len(binary_data)} bytes')

# Encode to base64 for transmission
b64_data = base64.b64encode(binary_data).decode('ascii')
print(f'Base64 size: {len(b64_data)} bytes')

for camera_id, host in [('yhs3017-2', '10.0.0.252'), ('yhs3017-1', '10.0.0.246')]:
    print(f'\n=== Uploading to {camera_id} ({host}) ===')

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=22, username='root', password='',
                       look_for_keys=False, allow_agent=False, timeout=30)

        # Send base64 data
        remote_path = '/tmp/camcontrol-uploader.b64'
        cmd = f'cat > {remote_path}'

        transport = client.get_transport()
        channel = transport.open_session(timeout=30)
        channel.exec_command(cmd)

        print(f'Sending {len(b64_data)} bytes via cat...')
        channel.sendall(b64_data.encode() + b'\n')
        channel.shutdown_write()

        # Read response
        exit_code = channel.recv_exit_status()
        print(f'Upload exit code: {exit_code}')

        # Decode and move
        _, _, _ = client.exec_command(f'base64 -d {remote_path} > /home/yi-hack-v3/camcontrol/camcontrol-uploader', timeout=30)
        _, _, _ = client.exec_command(f'chmod +x /home/yi-hack-v3/camcontrol/camcontrol-uploader', timeout=10)
        _, _, _ = client.exec_command(f'rm -f {remote_path}', timeout=10)

        # Verify
        _, stdout, _ = client.exec_command('ls -la /home/yi-hack-v3/camcontrol/camcontrol-uploader', timeout=10)
        verify = stdout.read().decode().strip()
        if 'camcontrol-uploader' in verify:
            print(f'✓ Upload verified')

            # Start uploader
            import time
            start_cmd = 'nohup /home/yi-hack-v3/camcontrol/camcontrol-uploader > /tmp/camcontrol-uploader.log 2>&1 &'
            _, _, _ = client.exec_command(start_cmd, timeout=5)

            time.sleep(3)

            # Check if running
            _, stdout, _ = client.exec_command('ps | grep camcontrol-uploader | grep -v grep', timeout=10)
            running = stdout.read().decode().strip()
            if running:
                print(f'✓ Uploader is RUNNING')
            else:
                print(f'? Checking logs...')
                _, stdout, _ = client.exec_command('tail -10 /tmp/camcontrol-uploader.log 2>/dev/null', timeout=5)
                logs = stdout.read().decode().strip()
                if logs:
                    print(logs[:300])
        else:
            print(f'✗ Verification failed')

        client.close()
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')

print('\nDone')
