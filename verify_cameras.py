#!/usr/bin/env python3
"""Verify camera provisioning state."""

import paramiko
import json

for camera_id, host in [('yhs3017-1', '10.0.0.246'), ('yhs3017-2', '10.0.0.252')]:
    print(f'\n=== {camera_id} ({host}) ===')

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=22, username='root', password='',
                       look_for_keys=False, allow_agent=False, timeout=30)

        # Check if uploader binary exists
        _, stdout, _ = client.exec_command('ls -la /home/yi-hack-v3/camcontrol/camcontrol-uploader 2>&1', timeout=10)
        uploader_status = stdout.read().decode().strip()
        uploader_ok = 'camcontrol-uploader' in uploader_status and '-rwx' in uploader_status
        print(f'  Uploader installed: {"YES" if uploader_ok else "NO"}')

        # Check configuration
        _, stdout, _ = client.exec_command('cat /home/yi-hack-v3/camcontrol/camcontrol.conf 2>/dev/null', timeout=10)
        config = stdout.read().decode().strip()

        if config:
            print(f'  Configuration found:')
            # Parse key settings
            for line in config.split('\n'):
                if any(k in line for k in ['api_endpoint', 'camera_id', 'push_interval', 'api_key']):
                    key, _, value = line.partition('=')
                    if 'api_key' in key or 'password' in key or 'psk' in key:
                        print(f'    {key}=***')
                    else:
                        print(f'    {key}={value}')
        else:
            print(f'  Configuration: NOT INSTALLED')

        # Check disk space
        _, stdout, _ = client.exec_command('df / | tail -1 | awk "{print $5}"', timeout=10)
        percent = stdout.read().decode().strip()
        print(f'  Disk usage: {percent}')

        # Check if uploader process is running
        _, stdout, _ = client.exec_command('ps | grep camcontrol-uploader | grep -v grep', timeout=10)
        running = stdout.read().decode().strip()
        if running:
            print(f'  Uploader process: RUNNING')
        else:
            print(f'  Uploader process: not running')

        client.close()
    except Exception as e:
        print(f'  Error: {type(e).__name__}: {e}')
