#!/bin/sh
# Boot entry point for the on-camera CamControl configuration package.
#
# Runs detached so the camera's own init never waits on it. Order matters:
# an SD card drops in new settings first, those settings are applied, and the
# setup AP is raised only if the camera could not get onto its wifi network
# (or the operator pinned it on). That makes a wrong wifi password
# self-recovering instead of bricking access to the camera.

. /home/yi-hack-v3/camcontrol/bin/camcontrol-common.sh

CC_BIN="$CAMCONTROL_DIR/bin"
SD_CONF_CANDIDATES="/tmp/sd/camcontrol.conf /tmp/sd/yi-hack-v3/camcontrol.conf"

# An SD card is the recovery channel: if the portal and wifi are both
# unreachable, dropping a camcontrol.conf on the card reconfigures the camera
# on the next power cycle.
cc_import_sd_config() {
    for _sd in $SD_CONF_CANDIDATES; do
        [ -f "$_sd" ] || continue
        cc_log "boot: importing configuration from SD card"
        # Same key=value grammar as the on-flash config, so this is a merge of
        # only the keys the card actually specifies.
        while IFS= read -r _line; do
            case "$_line" in
                ''|'#'*) continue ;;
                *=*)
                    _key=${_line%%=*}
                    _val=${_line#*=}
                    cc_set "$_key" "$_val"
                    ;;
            esac
        done <"$_sd"
        # Renamed so a card left in the slot stops overriding later changes
        # made from the portal.
        mv "$_sd" "$_sd.applied" 2>/dev/null
        cc_log "boot: SD configuration imported"
        return 0
    done
    return 1
}

cc_wifi_associated() {
    _iface=$(cc_wifi_iface)
    cc_tool ifconfig "$_iface" 2>/dev/null | grep -q 'inet addr:' && return 0
    return 1
}

cc_run() {
    cc_log "boot: camcontrol starting"
    cc_import_sd_config

    sh "$CC_BIN/camcontrol-apply.sh" all

    _always=$(cc_get ap_always 0)
    if [ "$_always" = "1" ]; then
        cc_log "boot: ap_always set, raising setup AP"
        sh "$CC_BIN/camcontrol-portal.sh" start
        return 0
    fi

    # Give the firmware's normal wifi bring-up a chance before overriding it.
    # This firmware associates well after its init finishes, so the default
    # wait is generous -- expiring it early is what strands a healthy camera.
    _wait=$(cc_get wifi_wait_seconds 120)
    case "$_wait" in
        ''|*[!0-9]*) _wait=120 ;;
    esac
    _waited=0
    while [ "$_waited" -lt "$_wait" ]; do
        if cc_wifi_associated; then
            cc_log "boot: wifi associated"
            sh "$CC_BIN/camcontrol-apply.sh" announce
            while :; do
                sh "$CC_BIN/camcontrol-apply.sh" push >/dev/null 2>&1
                cc_log "push: worker exited; restarting"
                sleep 5
            done
        fi
        sleep 5
        _waited=$((_waited + 5))
    done

    # camcontrol only owns the radio once it has been given wifi settings of
    # its own. With no ssid configured the firmware's wifi is in charge, and
    # replacing it with a setup AP would break a camera that simply boots
    # slowly rather than recovering one that is misconfigured.
    if [ -z "$(cc_get wifi_ssid "")" ]; then
        cc_log "boot: no wifi_ssid set, leaving firmware wifi alone"
        return 0
    fi

    cc_log "boot: wifi did not associate, raising setup AP"
    if sh "$CC_BIN/camcontrol-portal.sh" start; then
        _timeout=$(cc_get ap_timeout_seconds 900)
        case "$_timeout" in
            ''|*[!0-9]*) _timeout=0 ;;
        esac
        if [ "$_timeout" -gt 0 ]; then
            # Reboot back into client mode so a camera left in setup mode
            # eventually retries the real network on its own.
            (sleep "$_timeout"; cc_log "boot: AP timeout, rebooting"; reboot) \
                >/dev/null 2>&1 &
        fi
    fi
}

cc_run &
