#!/bin/sh
# Applies the persisted CamControl configuration. Invoked at boot by
# camcontrol-boot.sh, which is why every step is wrapped so that a failure
# degrades into "old setting keeps working" instead of a camera that never
# finishes booting.

. /home/yi-hack-v3/camcontrol/bin/camcontrol-common.sh

cc_apply_ssh_port() {
    _port=$(cc_get ssh_port 22)
    case "$_port" in
        ''|*[!0-9]*) cc_log "ssh: ignoring non-numeric port"; return 0 ;;
    esac
    [ "$_port" -ge 1 ] 2>/dev/null && [ "$_port" -le 65535 ] 2>/dev/null || {
        cc_log "ssh: port out of range"
        return 0
    }

    # dropbear has no config file on this firmware; the port is an argv flag,
    # so switching ports means relaunching it.
    _running=$(ps 2>/dev/null | grep '[d]ropbear' | sed -n '1p')
    if [ -n "$_running" ]; then
        case "$_running" in
            *"-p $_port"*) cc_log "ssh: already on requested port"; return 0 ;;
        esac
    fi

    if ! cc_has dropbear; then
        cc_log "ssh: dropbear not found, leaving port unchanged"
        return 0
    fi

    for _pid in $(ps 2>/dev/null | grep '[d]ropbear' | awk '{print $1}'); do
        kill "$_pid" 2>/dev/null
    done
    sleep 1
    cc_tool dropbear -p "$_port" >/dev/null 2>&1 &
    cc_log "ssh: dropbear restarted on port $_port"
}

cc_apply_wifi_client() {
    _ssid=$(cc_get wifi_ssid "")
    [ -n "$_ssid" ] || { cc_log "wifi: no ssid configured, skipping"; return 0; }
    _psk=$(cc_get wifi_psk "")
    _iface=$(cc_wifi_iface)
    _conf=/tmp/camcontrol-wpa.conf

    {
        echo "ctrl_interface=/var/run/wpa_supplicant"
        echo "update_config=1"
        echo "network={"
        printf '    ssid="%s"\n' "$_ssid"
        if [ -n "$_psk" ]; then
            printf '    psk="%s"\n' "$_psk"
        else
            echo "    key_mgmt=NONE"
        fi
        echo "}"
    } >"$_conf" 2>/dev/null
    chmod 600 "$_conf" 2>/dev/null

    # Persist for the firmware's own wifi bring-up too, so a later reboot that
    # skips this script still joins the right network.
    if [ -f /etc/wpa_supplicant.conf ] || [ -d /etc ]; then
        cp "$_conf" /etc/wpa_supplicant.conf 2>/dev/null
        chmod 600 /etc/wpa_supplicant.conf 2>/dev/null
    fi
    cc_log "wifi: client profile written for interface $_iface"
}

cc_apply_admin_account() {
    _user=$(cc_get admin_user root)
    _password=$(cc_get admin_password "")
    [ -n "$_password" ] || { cc_log "account: no password set, skipping"; return 0; }

    if cc_has chpasswd; then
        printf '%s:%s\n' "$_user" "$_password" | cc_tool chpasswd >/dev/null 2>&1 &&
            cc_log "account: password updated for $_user" && return 0
    fi
    if cc_has passwd; then
        printf '%s\n%s\n' "$_password" "$_password" |
            cc_tool passwd "$_user" >/dev/null 2>&1 &&
            cc_log "account: password updated for $_user" && return 0
    fi
    cc_log "account: no usable chpasswd/passwd, password unchanged"
}

# Tells the gateway where this camera currently is. This is the only
# camera->gateway call in the system and it is strictly best-effort: the
# gateway still works purely by polling if this never succeeds.
cc_announce() {
    _endpoint=$(cc_get api_endpoint "")
    [ -n "$_endpoint" ] || return 0
    _key=$(cc_get api_key "")
    _id=$(cc_get camera_id "")
    _iface=$(cc_wifi_iface)
    _ip=$(cc_tool ifconfig "$_iface" 2>/dev/null |
        sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p' | sed -n '1p')
    _port=$(cc_get ssh_port 22)

    cc_has wget || { cc_log "announce: no wget, skipping"; return 0; }

    _body=$(printf '{"camera_id":"%s","address":"%s","ssh_port":%s}' \
        "$_id" "$_ip" "$_port")
    cc_tool wget -q -O /dev/null \
        --header="Content-Type: application/json" \
        --header="X-Camera-Key: $_key" \
        --post-data="$_body" \
        "$_endpoint/api/cameras/announce" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        cc_log "announce: reported to gateway"
    else
        cc_log "announce: gateway unreachable (non-fatal)"
    fi
}

cc_push_snapshots() {
    _endpoint=$(cc_get api_endpoint "")
    _key=$(cc_get api_key "")
    _id=$(cc_get camera_id "")
    _interval=$(cc_get push_interval_seconds 5)
    case "$_interval" in ''|*[!0-9]*|0) return 0 ;; esac
    [ -n "$_endpoint" ] && [ -n "$_key" ] && [ -n "$_id" ] || return 0
    _uploader="$CAMCONTROL_DIR/bin/camcontrol-uploader"
    [ -x "$_uploader" ] || { cc_log "push: uploader missing, skipping"; return 0; }

    while :; do
        if [ -s /tmp/view ]; then
            case "$_endpoint" in
                http://*)
                    _address=${_endpoint#http://}
                    case "$_address" in
                        *:*) _host=${_address%:*}; _port=${_address##*:} ;;
                        *) _host=$_address; _port=80 ;;
                    esac
                    set -- $(ls -l /tmp/view 2>/dev/null)
                    _length=$5
                    case "$_length" in
                        ''|*[!0-9]*) cc_log "push: could not measure preview buffer" ;;
                        *) {
                            printf 'POST /api/cameras/%s/push-snapshot HTTP/1.1\r\n' "$_id"
                            printf 'Host: %s\r\n' "$_host"
                            printf 'Content-Type: video/h264\r\n'
                            printf 'Content-Length: %s\r\n' "$_length"
                            printf 'X-Camera-Key: %s\r\n' "$_key"
                            printf 'Connection: close\r\n\r\n'
                            cc_tool dd if=/tmp/view bs="$_length" count=1 2>/dev/null
                        } | cc_tool nc -w 15 "$_host" "$_port" >/dev/null 2>&1 ;;
                    esac
                    ;;
                *)
                    "$_uploader" \
                        -endpoint "$_endpoint/api/cameras/$_id/push-snapshot" \
                        -key "$_key" \
                        -file /tmp/view >/dev/null 2>&1
                    ;;
            esac
        fi
        sleep "$_interval"
    done
}

cc_apply_remote_http() {
    _port=$(cc_get remote_http_port 0)
    case "$_port" in ''|*[!0-9]*|0) return 0 ;; esac
    [ "$_port" -ge 1024 ] 2>/dev/null && [ "$_port" -le 65535 ] 2>/dev/null || {
        cc_log "remote-http: port out of range"
        return 0
    }

    _relay="$CAMCONTROL_DIR/bin/camcontrol-uploader"
    _pidfile=/tmp/camcontrol-remote-http.pid
    [ -x "$_relay" ] || { cc_log "remote-http: relay binary missing"; return 0; }
    if [ -f "$_pidfile" ]; then
        _pid=$(cat "$_pidfile" 2>/dev/null)
        if kill -0 "$_pid" 2>/dev/null; then
            cc_log "remote-http: already listening on $_port"
            return 0
        fi
        rm -f "$_pidfile"
    fi
    "$_relay" -listen ":$_port" -target "127.0.0.1:80" >/dev/null 2>&1 &
    echo "$!" >"$_pidfile"
    cc_log "remote-http: forwarding $_port to local port 80"
}

cc_apply_all() {
    cc_log "apply: starting"
    cc_apply_ssh_port
    cc_apply_wifi_client
    cc_apply_admin_account
    cc_apply_remote_http
    cc_log "apply: done"
}

case "${1:-all}" in
    ssh) cc_apply_ssh_port ;;
    wifi) cc_apply_wifi_client ;;
    account) cc_apply_admin_account ;;
    remote-http) cc_apply_remote_http ;;
    announce) cc_announce ;;
    push) cc_push_snapshots ;;
    *) cc_apply_all ;;
esac
