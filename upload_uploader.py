#!/usr/bin/env python3
"""Direct upload of uploader binary to cameras."""

import paramiko
from pathlib import Path

uploader_file = Path('src/camera_bridge/oncam/camcontrol-uploader')
if not uploader_file.exists():
    print(f'ERROR: Uploader binary not found at {uploader_file}')
    exit(1)

binary_data = uploader_file.read_bytes()
print(f'Binary size: {len(binary_data)} bytes')

for camera_id, host in [('yhs3017-2', '10.0.0.252'), ('yhs3017-1', '10.0.0.246')]:
    print(f'\n=== Uploading to {camera_id} ({host}) ===')

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=22, username='root', password='',
                       look_for_keys=False, allow_agent=False, timeout=30)

        # Use SFTP to upload
        sftp = client.open_sftp()
        remote_path = '/home/yi-hack-v3/camcontrol/camcontrol-uploader'

        try:
            print(f'Uploading {len(binary_data)} bytes to {remote_path}...')
            with sftp.file(remote_path, 'wb') as f:
                f.write(binary_data)
            print(f'Upload complete')

            # Make executable
            client.exec_command(f'chmod +x {remote_path}')
            print(f'Made executable')

            # Verify
            _, stdout, _ = client.exec_command(f'ls -la {remote_path}', timeout=10)
            print(f'Verified: {stdout.read().decode().strip()}')

            # Start uploader
            _, _, stderr = client.exec_command(
                f'nohup {remote_path} > /tmp/camcontrol-uploader.log 2>&1 &',
                timeout=5
            )
            err = stderr.read().decode().strip()
            if err:
                print(f'Start stderr: {err}')

            # Give it a moment to start
            import time
            time.sleep(2)

            # Check if running
            _, stdout, _ = client.exec_command('ps | grep camcontrol-uploader | grep -v grep', timeout=10)
            running = stdout.read().decode().strip()
            if running:
                print(f'✓ Uploader is RUNNING')
            else:
                print(f'? Uploader status unclear')
                # Check logs
                _, stdout, _ = client.exec_command('tail -20 /tmp/camcontrol-uploader.log 2>/dev/null', timeout=5)
                logs = stdout.read().decode().strip()
                if logs:
                    print(f'  Logs: {logs[:200]}')

        finally:
            sftp.close()

        client.close()
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')

print('\nDone')
