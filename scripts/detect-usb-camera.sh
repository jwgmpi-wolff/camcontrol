#!/usr/bin/env bash
# Detect UVC-compatible USB cameras on Linux.
# Does not modify any device, firmware, or driver.
set -euo pipefail

found=0

echo "=== /dev/video* devices ==="
for dev in /dev/video*; do
    [ -e "$dev" ] || { echo "(none found)"; break; }
    found=1
    name_file="/sys/class/video4linux/$(basename "$dev")/name"
    name=$(cat "$name_file" 2>/dev/null || echo "unknown")
    printf "%-14s  %s\n" "$dev" "$name"
done

echo ""
echo "=== USB device list (lsusb) ==="
if command -v lsusb &>/dev/null; then
    lsusb
else
    echo "(lsusb not available; install usbutils)"
fi

if command -v v4l2-ctl &>/dev/null; then
    echo ""
    echo "=== UVC capabilities (v4l2-ctl) ==="
    for dev in /dev/video*; do
        [ -e "$dev" ] || break
        echo "--- $dev ---"
        v4l2-ctl -d "$dev" --info 2>/dev/null || true
        v4l2-ctl -d "$dev" --list-formats-ext 2>/dev/null || true
    done
else
    echo ""
    echo "(v4l2-ctl not available; install v4l-utils for detailed format info)"
fi

if [ "$found" -eq 0 ]; then
    echo "No /dev/video* devices found."
    echo "Check: lsusb | grep -i camera"
    exit 2
fi

echo ""
echo "Set CAMERA_DEVICE_PATH to the device path above, then run:"
echo "  python -m camera_bridge.main --detect-only"
