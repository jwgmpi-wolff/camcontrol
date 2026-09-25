#!/usr/bin/env python3
"""Aggressive cleanup on yhs3017-1 to free disk space."""

import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('10.0.0.246', port=22, username='root', password='', look_for_keys=False, allow_agent=False, timeout=30)

# Check for video recordings or large media files
cmds = [
    ('Recording dir:', 'du -sh /home/yi-hack-v3/media 2>/dev/null || echo none'),
    ('SD card:', 'du -sh /mnt/sd* 2>/dev/null || echo none'),
    ('Large files:', 'find /home -maxdepth 3 -type f -size +50M 2>/dev/null | head -5'),
]

for label, cmd in cmds:
    _, stdout, _ = client.exec_command(cmd, timeout=15)
    out = stdout.read().decode().strip()
    if out:
        print(f'{label}')
        print(out)
        print()

# Try deleting recordings
cmds_clean = [
    'rm -f /home/yi-hack-v3/media/* 2>/dev/null; true',
    'rm -f /home/yi-hack-v3/*.mp4 /home/yi-hack-v3/*.avi 2>/dev/null; true',
    'rm -rf /mnt/sd/recordings 2>/dev/null; true',
]

for cmd in cmds_clean:
    _, stdout, stderr = client.exec_command(cmd, timeout=15)
    stdout.read(); stderr.read()

# Final check
_, stdout, _ = client.exec_command('df / | tail -1 | awk "{print $5}"', timeout=10)
percent = stdout.read().decode().strip()
print(f'Final yhs3017-1: {percent} used')

client.close()
