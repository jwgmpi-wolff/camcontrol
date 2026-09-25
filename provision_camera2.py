#!/usr/bin/env python3
"""Provision camera 2 for gateway uploads."""

import os
import subprocess
from pathlib import Path

# Read master key
master_key_file = Path(os.environ['TEMP']) / 'camcontrol-gateway-master.key'
if not master_key_file.exists():
    print('ERROR: Master key not found')
    exit(1)

master_key = master_key_file.read_text().strip()
os.environ['CAMCONTROL_API_KEY'] = master_key

# For yhs3017-2 only (camera 1 has insufficient disk space)
camera_id = 'yhs3017-2'

commands = [
    ['install', '--camera', camera_id],
    ['set', '--camera', camera_id,
     '--api-endpoint', 'https://camcontrol-wolff.azurewebsites.net',
     '--camera-id', camera_id,
     '--push-interval-seconds', '5'],
    ['reboot', '--camera', camera_id],
]

python_exe = Path('.venv/Scripts/python.exe')

for cmd in commands:
    step_name = cmd[0]
    print(f'\n{step_name.upper()} {camera_id}...')

    result = subprocess.run(
        [str(python_exe), '-m', 'camera_bridge.provision_cli',
         '--config', 'config/cameras.json'] + cmd,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f'✓ {step_name} succeeded')
    else:
        print(f'✗ {step_name} failed (exit {result.returncode})')
        if result.stdout:
            print('  stdout:', result.stdout[:200])
        if result.stderr:
            print('  stderr:', result.stderr[:200])
        break

print(f'\nWaiting 90 seconds for {camera_id} to reboot...')
import time
time.sleep(90)

# Verify
print(f'\nVerifying {camera_id} is accessible...')
import paramiko
try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('10.0.0.252', port=22, username='root', password='',
                   look_for_keys=False, allow_agent=False, timeout=30)
    _, stdout, _ = client.exec_command('cat /home/yi-hack-v3/camcontrol/camcontrol.conf 2>/dev/null | grep api_endpoint', timeout=10)
    config = stdout.read().decode().strip()
    if 'camcontrol-wolff' in config:
        print(f'✓ {camera_id} is configured with gateway endpoint')
    else:
        print(f'? Configuration unclear: {config[:100]}')
    client.close()
except Exception as e:
    print(f'✗ Verification failed: {type(e).__name__}')

print('\nDONE: Camera yhs3017-2 provisioned')
print('NOTE: Camera yhs3017-1 has insufficient disk space (92% full) and cannot be provisioned without manual cleanup')
