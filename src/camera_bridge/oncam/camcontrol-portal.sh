#!/bin/sh
# Raises the camera's own configuration access point and serves the portal
# on it, so a phone can reconfigure the camera with no LAN and no gateway.
#
# This firmware has no hostapd, so the AP is wpa_supplicant's own AP mode
# (mode=2) using the Realtek build in /home/base/tools. It also has no DHCP
# server (no udhcpd applet), so a client must set a static address --
# cc_ap_client_hint() reports exactly what to use.
#
# Bringing up the AP tears down the wifi client connection, which is the one
# irreversible-looking step on a headless camera. Every entry point here
# arms a reboot watchdog *first*: if anything fails, the camera reboots back
# into its normal client configuration on its own.

. /home/yi-hack-v3/camcontrol/bin/camcontrol-common.sh

CC_BIN="$CAMCONTROL_DIR/bin"

cc_ap_ssid() {
    _ssid=$(cc_get ap_ssid "")
    [ -n "$_ssid" ] || _ssid="camcontrol-$(cc_mac_suffix)"
    printf '%s' "$_ssid"
}

# Reboots the camera after N seconds unless the watchdog is disarmed. Armed
# before any wifi change so a failed AP attempt always self-recovers.
cc_arm_watchdog() {
    _seconds="$1"
    case "$_seconds" in
        ''|*[!0-9]*) return 0 ;;
    esac
    [ "$_seconds" -gt 0 ] || return 0
    rm -f /tmp/camcontrol-watchdog-disarm 2>/dev/null
    (
        sleep "$_seconds"
        if [ ! -f /tmp/camcontrol-watchdog-disarm ]; then
            cc_log "watchdog: firing, rebooting to restore client wifi"
            cc_tool reboot
        fi
    ) >/dev/null 2>&1 &
    cc_log "watchdog: armed for ${_seconds}s"
}

cc_disarm_watchdog() {
    : >/tmp/camcontrol-watchdog-disarm 2>/dev/null
    cc_log "watchdog: disarmed"
}

cc_ap_frequency() {
    case "$1" in
        1) printf 2412 ;; 2) printf 2417 ;; 3) printf 2422 ;; 4) printf 2427 ;;
        5) printf 2432 ;; 6) printf 2437 ;; 7) printf 2442 ;; 8) printf 2447 ;;
        9) printf 2452 ;; 10) printf 2457 ;; 11) printf 2462 ;; *) printf 2437 ;;
    esac
}

cc_ap_client_hint() {
    _addr=$(cc_get ap_address 192.168.8.1)
    _port=$(cc_get portal_port 8080)
    _base=$(printf '%s' "$_addr" | cut -d. -f1-3)
    cc_log "ap: no DHCP server on this firmware -- set a static address on the"
    cc_log "ap: client, e.g. $_base.50 / 255.255.255.0 / gateway $_addr"
    cc_log "ap: then open http://$_addr:$_port/"
}

cc_ap_start() {
    _iface=$(cc_wifi_iface)
    _ssid=$(cc_ap_ssid)
    _psk=$(cc_get ap_psk "")
    _addr=$(cc_get ap_address 192.168.8.1)
    _channel=$(cc_get ap_channel 6)

    if [ ${#_psk} -lt 8 ]; then
        # An open AP would let anyone in range rewrite the camera's creds.
        cc_log "ap: refusing to start, ap_psk must be at least 8 characters"
        return 1
    fi
    if ! cc_has wpa_supplicant; then
        cc_log "ap: wpa_supplicant not found"
        return 1
    fi

    _conf=/tmp/camcontrol-ap.conf
    {
        echo "ctrl_interface=/var/run/wpa_supplicant"
        echo "update_config=1"
        echo "network={"
        printf '    ssid="%s"\n' "$_ssid"
        echo "    mode=2"
        echo "    key_mgmt=WPA-PSK"
        echo "    proto=RSN"
        echo "    pairwise=CCMP"
        echo "    group=CCMP"
        printf '    psk="%s"\n' "$_psk"
        printf '    frequency=%s\n' "$(cc_ap_frequency "$_channel")"
        echo "}"
    } >"$_conf" 2>/dev/null
    chmod 600 "$_conf" 2>/dev/null

    for _pid in $(ps 2>/dev/null | grep '[w]pa_supplicant' | awk '{print $1}'); do
        kill "$_pid" 2>/dev/null
    done
    sleep 2

    cc_tool wpa_supplicant -B -i "$_iface" -c "$_conf" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        cc_log "ap: wpa_supplicant refused AP mode on this driver"
        return 1
    fi
    sleep 3

    cc_tool ifconfig "$_iface" "$_addr" netmask 255.255.255.0 up 2>/dev/null
    cc_ap_client_hint
    cc_log "ap: up as '$_ssid' on $_addr"
    return 0
}

# Everything the portal needs before it can serve. Checked *before* the AP
# tears down the wifi client: an AP nobody can log in to is strictly worse
# than leaving the camera on the network it already reached.
cc_portal_ready() {
    if ! cc_has nc; then
        cc_log "portal: no nc applet, portal cannot be served"
        return 1
    fi
    if [ -z "$(cc_get admin_password "")" ]; then
        cc_log "portal: refusing to start without a login password"
        return 1
    fi
    return 0
}

cc_portal_start() {
    cc_portal_ready || return 1
    for _pid in $(ps 2>/dev/null | grep '[c]amcontrol-httpd.sh serve' |
        awk '{print $1}'); do
        kill "$_pid" 2>/dev/null
    done
    sh "$CC_BIN/camcontrol-httpd.sh" serve >/dev/null 2>&1 &
    cc_log "portal: serving on port $(cc_get portal_port 8080)"
    return 0
}

cc_portal_stop() {
    for _pid in $(ps 2>/dev/null | grep -E '[c]amcontrol-httpd.sh|[n]c -l -p' |
        awk '{print $1}'); do
        kill "$_pid" 2>/dev/null
    done
}

# The AP config lives in /tmp and the firmware re-applies its own wifi on
# boot, so rebooting is the shortest path back to client mode. Used when the
# AP came up but the portal did not, instead of stranding the camera until
# the watchdog fires.
cc_ap_abort() {
    cc_portal_stop
    cc_log "ap: rebooting now to restore client wifi"
    cc_tool reboot
}

case "${1:-start}" in
    start)
        if ! cc_portal_ready; then
            cc_log "ap: not raising setup AP, portal cannot serve"
            exit 1
        fi
        cc_arm_watchdog "$(cc_get ap_timeout_seconds 900)"
        if cc_ap_start; then
            cc_portal_start || cc_ap_abort
        else
            cc_log "ap: bring-up failed; leaving watchdog armed to recover"
        fi
        ;;
    test)
        if ! cc_portal_ready; then
            cc_log "test: portal cannot serve, not touching wifi"
            exit 1
        fi
        # Deliberately short watchdog: proves AP mode works on this driver
        # without risking a camera that never comes back.
        cc_arm_watchdog "${2:-180}"
        if cc_ap_start; then
            cc_portal_start || cc_ap_abort
            cc_log "test: AP and portal started, watchdog still armed"
        else
            cc_log "test: AP bring-up failed"
        fi
        ;;
    portal)
        cc_portal_start
        ;;
    stop)
        cc_portal_stop
        ;;
    disarm)
        cc_disarm_watchdog
        ;;
esac
