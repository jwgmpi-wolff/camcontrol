#!/usr/bin/env python3
"""Clean up disk space on remote cameras."""

import paramiko
import time

for camera_id, host in [('yhs3017-1', '10.0.0.246'), ('yhs3017-2', '10.0.0.252')]:
    print(f'\n=== Cleaning {camera_id} ({host}) ===')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=22, username='root', password='', look_for_keys=False, allow_agent=False, timeout=30)

        # Try to identify and remove large unused files
        commands = [
            'rm -rf /tmp/yi-hack* 2>/dev/null; true',
            'rm -rf /tmp/SD* 2>/dev/null; true',
            'rm -rf /var/log/* 2>/dev/null; true',
            'rm -rf /var/tmp/* 2>/dev/null; true',
            'rm -f /tmp/*.tar.gz /tmp/*.tar 2>/dev/null; true',
            'rm -rf /tmp/apt* 2>/dev/null; true',
        ]

        for cmd in commands:
            _, stdout, stderr = client.exec_command(cmd, timeout=15)
            stdout.read(); stderr.read()

        time.sleep(2)

        # Check space after cleanup
        _, stdout, _ = client.exec_command('df / | tail -1 | awk "{print $5}"', timeout=10)
        percent = stdout.read().decode().strip()
        print(f'After cleanup: {percent} used')

        client.close()
    except Exception as e:
        print(f'Error: {type(e).__name__}: {e}')
