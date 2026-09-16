#!/bin/sh
# Minimal HTTP server for the on-camera configuration portal.
#
# This firmware has no busybox httpd and no CGI-capable web server (lwsws is
# static-file only), so the portal is served directly over busybox nc, which
# does have -l/-p/-e on this build. nc execs this script per connection with
# the socket on stdin/stdout; `serve` is the accept loop.
#
# Secrets are never rendered back into the page: each secret field shows only
# whether a value is stored, and a blank submission keeps the stored value.

. /home/yi-hack-v3/camcontrol/bin/camcontrol-common.sh

SELF="$CAMCONTROL_DIR/bin/camcontrol-httpd.sh"

cc_html() {
    printf '%s' "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g'
}

cc_urldecode() {
    _v=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/+/ /g; s/%/\\x/g')
    printf '%b' "$_v"
}

cc_field() {
    _raw=$(printf '%s' "$CC_BODY" | tr '&' '\n' | sed -n "s/^$1=//p" | sed -n '1p')
    cc_urldecode "$_raw"
}

cc_isset_label() {
    if [ -n "$(cc_get "$1" "")" ]; then
        printf 'stored -- leave blank to keep it'
    else
        printf 'not set'
    fi
}

cc_expected_auth() {
    _u=$(cc_get admin_user root)
    _p=$(cc_get admin_password "")
    [ -n "$_p" ] || return 1
    printf 'Basic %s' \
        "$(printf '%s:%s' "$_u" "$_p" | cc_tool base64 | tr -d '\n')"
}

cc_send_headers() {
    printf 'HTTP/1.0 %s\r\n' "$1"
    printf 'Content-Type: text/html; charset=utf-8\r\n'
    printf 'Connection: close\r\n'
    printf 'Cache-Control: no-store\r\n'
    [ -n "${2:-}" ] && printf '%s\r\n' "$2"
    printf '\r\n'
}

cc_render_page() {
    cc_send_headers '200 OK'
    cat <<HTML_HEAD
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CamControl camera setup</title>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;background:#111;color:#eee;
      margin:0;padding:16px;}
 form{max-width:520px;margin:0 auto;}
 h1{font-size:1.25rem;} h2{font-size:1rem;margin-top:22px;color:#8ab4f8;}
 label{display:block;margin-top:12px;font-size:.85rem;color:#bbb;}
 input[type=text],input[type=password]{width:100%;padding:10px;margin-top:4px;
      border-radius:6px;border:1px solid #444;background:#1c1c1c;color:#eee;
      box-sizing:border-box;}
 .hint{font-size:.72rem;color:#888;margin-top:2px;}
 .row{margin-top:18px;display:flex;gap:8px;}
 button{flex:1;padding:12px;border:0;border-radius:6px;font-size:.95rem;}
 .save{background:#2d6cdf;color:#fff;} .reboot{background:#c2410c;color:#fff;}
 .msg{padding:10px;border-radius:6px;margin-top:12px;background:#14532d;}
 .err{padding:10px;border-radius:6px;margin-top:12px;background:#7f1d1d;}
</style></head><body><form method="post" action="/">
<h1>CamControl camera setup</h1>
HTML_HEAD

    if [ -n "$CC_ERROR" ]; then
        printf '<div class="err">%s</div>\n' "$(cc_html "$CC_ERROR")"
    elif [ -n "$CC_MESSAGE" ]; then
        printf '<div class="msg">%s</div>\n' "$(cc_html "$CC_MESSAGE")"
    fi

    cat <<HTML_BODY
<h2>Access</h2>
<label>SSH port<input type="text" name="ssh_port" inputmode="numeric"
 value="$(cc_html "$(cc_get ssh_port 22)")"></label>
<label>Login account<input type="text" name="admin_user"
 value="$(cc_html "$(cc_get admin_user root)")"></label>
<label>Login password<input type="password" name="admin_password"
 autocomplete="new-password">
<div class="hint">$(cc_isset_label admin_password)</div></label>

<h2>Wi-Fi network to join</h2>
<label>SSID<input type="text" name="wifi_ssid"
 value="$(cc_html "$(cc_get wifi_ssid "")")"></label>
<label>Password<input type="password" name="wifi_psk"
 autocomplete="new-password">
<div class="hint">$(cc_isset_label wifi_psk)</div></label>

<h2>Gateway endpoint</h2>
<label>API endpoint<input type="text" name="api_endpoint" inputmode="url"
 value="$(cc_html "$(cc_get api_endpoint "")")">
<div class="hint">e.g. https://your-gateway.example.net</div></label>
<label>API key<input type="password" name="api_key"
 autocomplete="new-password">
<div class="hint">$(cc_isset_label api_key)</div></label>
<label>Camera id<input type="text" name="camera_id"
 value="$(cc_html "$(cc_get camera_id "")")"></label>

<h2>This setup access point</h2>
<label>AP name<input type="text" name="ap_ssid"
 value="$(cc_html "$(cc_get ap_ssid "")")"></label>
<label>AP password<input type="password" name="ap_psk"
 autocomplete="new-password">
<div class="hint">$(cc_isset_label ap_psk) -- minimum 8 characters</div></label>
<label><input type="checkbox" name="ap_always" value="1"
$( [ "$(cc_get ap_always 0)" = "1" ] && printf 'checked' )>
 Keep this setup AP on at every boot</label>
<div class="row">
 <button class="save" type="submit">Save</button>
 <button class="reboot" type="submit" name="reboot" value="1">Save &amp; reboot</button>
</div>
</form></body></html>
HTML_BODY
}

cc_save() {
    _ssh_port=$(cc_field ssh_port)
    _ap_psk=$(cc_field ap_psk)
    _api_endpoint=$(cc_field api_endpoint)

    case "$_ssh_port" in
        ''|*[!0-9]*) CC_ERROR="SSH port must be a number." ; return ;;
    esac
    if [ "$_ssh_port" -lt 1 ] || [ "$_ssh_port" -gt 65535 ]; then
        CC_ERROR="SSH port must be between 1 and 65535."
        return
    fi
    if [ -n "$_ap_psk" ] && [ ${#_ap_psk} -lt 8 ]; then
        CC_ERROR="Access point password must be at least 8 characters."
        return
    fi
    if [ -n "$_api_endpoint" ]; then
        case "$_api_endpoint" in
            http://*|https://*) ;;
            *) CC_ERROR="API endpoint must start with http:// or https://."
               return ;;
        esac
    fi

    cc_set ssh_port "$_ssh_port"
    cc_set wifi_ssid "$(cc_field wifi_ssid)"
    cc_set api_endpoint "$_api_endpoint"
    cc_set camera_id "$(cc_field camera_id)"
    cc_set ap_ssid "$(cc_field ap_ssid)"

    _admin_user=$(cc_field admin_user)
    [ -n "$_admin_user" ] && cc_set admin_user "$_admin_user"
    _v=$(cc_field wifi_psk); [ -n "$_v" ] && cc_set wifi_psk "$_v"
    _v=$(cc_field admin_password); [ -n "$_v" ] && cc_set admin_password "$_v"
    _v=$(cc_field api_key); [ -n "$_v" ] && cc_set api_key "$_v"
    [ -n "$_ap_psk" ] && cc_set ap_psk "$_ap_psk"

    if [ "$(cc_field ap_always)" = "1" ]; then
        cc_set ap_always 1
    else
        cc_set ap_always 0
    fi

    cc_log "portal: configuration saved"
    CC_MESSAGE="Saved. Reboot the camera to apply."
    if [ -n "$(cc_field reboot)" ]; then
        CC_MESSAGE="Saved. Rebooting now..."
        CC_REBOOT=1
    fi
}

cc_handle() {
    CC_MESSAGE=""
    CC_ERROR=""
    CC_BODY=""
    CC_REBOOT=0

    read -r _request || return 0
    _method=${_request%% *}

    _length=0
    _auth=""
    while IFS= read -r _line; do
        _line=$(printf '%s' "$_line" | tr -d '\r')
        [ -z "$_line" ] && break
        case "$_line" in
            [Cc]ontent-[Ll]ength:*)
                _length=$(printf '%s' "${_line#*:}" | tr -d ' ') ;;
            [Aa]uthorization:*)
                _auth=$(printf '%s' "${_line#*:}" | sed 's/^ *//') ;;
        esac
    done

    _expected=$(cc_expected_auth)
    if [ -z "$_expected" ]; then
        cc_send_headers '503 Service Unavailable'
        echo '<p>No login password is set on this camera.</p>'
        return 0
    fi
    if [ "$_auth" != "$_expected" ]; then
        cc_send_headers '401 Unauthorized' \
            'WWW-Authenticate: Basic realm="CamControl"'
        echo '<p>Authentication required.</p>'
        return 0
    fi

    if [ "$_method" = "POST" ]; then
        case "$_length" in
            ''|*[!0-9]*) _length=0 ;;
        esac
        [ "$_length" -gt 0 ] && CC_BODY=$(dd bs=1 count="$_length" 2>/dev/null)
        cc_save
    fi
    cc_render_page

    # Reboot last, after the response is already on the socket. Backgrounding
    # it instead would lose the reboot when this handler exits.
    if [ "$CC_REBOOT" = "1" ]; then
        cc_log "portal: rebooting on request"
        sleep 1
        cc_tool reboot
    fi
}

case "${1:-handle}" in
    serve)
        _port=$(cc_get portal_port 8080)
        cc_log "portal: nc listener starting on port $_port"
        while :; do
            cc_tool nc -l -p "$_port" -e "$SELF" >/dev/null 2>&1
            sleep 1
        done
        ;;
    *)
        cc_handle
        ;;
esac
