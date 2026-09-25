#!/bin/sh
# Shared helpers for the on-camera CamControl configuration package.
#
# Target is busybox ash on yi-hack-v3 (Hi3518e) -- POSIX only, no bashisms,
# no arrays, no [[ ]]. Every helper is best-effort: nothing in this package
# may ever stop the camera from finishing its own boot.

CAMCONTROL_DIR="${CAMCONTROL_DIR:-/home/yi-hack-v3/camcontrol}"
CAMCONTROL_CONF="${CAMCONTROL_CONF:-$CAMCONTROL_DIR/camcontrol.conf}"
CAMCONTROL_LOG="${CAMCONTROL_LOG:-/tmp/camcontrol-config.log}"

# A non-interactive SSH session gets a minimal PATH that contains none of the
# firmware's own binaries, which makes every tool look missing. Same library
# path the firmware uses for lwsws.
PATH="$PATH:/home/base/tools:/home/yi-hack-v3/bin:/home/yi-hack-v3/sbin:/sbin:/usr/sbin:/bin:/usr/bin"
export PATH
LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/home/lib:/home/yi-hack-v3/lib:/tmp/sd/yi-hack-v3/lib"
export LD_LIBRARY_PATH

cc_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$CAMCONTROL_LOG" 2>/dev/null
}

# Reads a single key. Deliberately never dumps the whole config, so secrets
# stay out of logs and out of any command that traces its arguments.
# This busybox build has no `head`, hence `sed -n 1p`.
cc_get() {
    _cc_value=$(sed -n "s/^$1=//p" "$CAMCONTROL_CONF" 2>/dev/null | sed -n '1p')
    if [ -z "$_cc_value" ]; then
        printf '%s' "$2"
    else
        printf '%s' "$_cc_value"
    fi
}

# Rewrites a single key in place, preserving every other line.
cc_set() {
    _cc_tmp="$CAMCONTROL_CONF.tmp.$$"
    [ -f "$CAMCONTROL_CONF" ] || : >"$CAMCONTROL_CONF" 2>/dev/null
    grep -v "^$1=" "$CAMCONTROL_CONF" 2>/dev/null >"$_cc_tmp"
    printf '%s=%s\n' "$1" "$2" >>"$_cc_tmp"
    mv "$_cc_tmp" "$CAMCONTROL_CONF" 2>/dev/null
    chmod 600 "$CAMCONTROL_CONF" 2>/dev/null
}

# Many of these tools exist only as busybox applets, with no symlink on PATH.
cc_has() {
    command -v "$1" >/dev/null 2>&1 && return 0
    busybox --list 2>/dev/null | grep -qx "$1" && return 0
    return 1
}

# Runs a tool directly when it is on PATH, otherwise as a busybox applet.
cc_tool() {
    _cc_cmd="$1"
    shift
    if command -v "$_cc_cmd" >/dev/null 2>&1; then
        "$_cc_cmd" "$@"
    else
        busybox "$_cc_cmd" "$@"
    fi
}

# First wireless interface the kernel admits to having.
cc_wifi_iface() {
    _cc_if=$(cc_get wifi_interface "")
    if [ -n "$_cc_if" ]; then
        printf '%s' "$_cc_if"
        return 0
    fi
    for _cc_if in wlan0 wlan1 ra0 apcli0; do
        if [ -e "/sys/class/net/$_cc_if" ]; then
            printf '%s' "$_cc_if"
            return 0
        fi
    done
    printf '%s' wlan0
}

# Last 6 hex digits of the wifi MAC, used to make the AP SSID unique.
cc_mac_suffix() {
    _cc_mac=$(cat "/sys/class/net/$(cc_wifi_iface)/address" 2>/dev/null)
    if [ -z "$_cc_mac" ]; then
        printf '%s' 000000
    else
        printf '%s' "$_cc_mac" | tr -d ':' | tail -c 7 | tr 'A-Z' 'a-z'
    fi
}
