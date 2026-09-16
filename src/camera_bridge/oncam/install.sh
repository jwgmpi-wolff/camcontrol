#!/bin/sh
# On-camera installer for the CamControl configuration package.
#
# Run from the staging directory the gateway uploaded (default
# /tmp/camcontrol-install). Idempotent: re-running upgrades the scripts and
# leaves camcontrol.conf, the boot hook and the generated AP password alone.
#
# Safety: the boot hook is a single guarded line appended to an existing
# startup script, the original is backed up first, and the hook itself only
# ever launches camcontrol-boot.sh in the background.

set -u

STAGE_DIR="${STAGE_DIR:-/tmp/camcontrol-install}"
CAMCONTROL_DIR="${CAMCONTROL_DIR:-/home/yi-hack-v3/camcontrol}"
CAMCONTROL_CONF="$CAMCONTROL_DIR/camcontrol.conf"
HOOK_MARKER="# camcontrol-config-hook"
HOOK_CANDIDATES="/home/yi-hack-v3/startup.sh
/home/yi-hack-v3/script/run.sh
/home/yi-hack-v3/etc/init.d/rcS
/home/init.sh
/etc/init.d/rcS"

say() {
    echo "camcontrol-install: $*"
}

say "staging directory $STAGE_DIR"
say "install directory  $CAMCONTROL_DIR"

mkdir -p "$CAMCONTROL_DIR/bin" 2>/dev/null || {
    say "FAILED: cannot create $CAMCONTROL_DIR (read-only filesystem?)"
    exit 1
}

for f in camcontrol-common.sh camcontrol-apply.sh camcontrol-portal.sh \
         camcontrol-httpd.sh camcontrol-boot.sh; do
    if [ ! -f "$STAGE_DIR/$f" ]; then
        say "FAILED: missing $f in staging directory"
        exit 1
    fi
    cp "$STAGE_DIR/$f" "$CAMCONTROL_DIR/bin/$f" || exit 1
    chmod 755 "$CAMCONTROL_DIR/bin/$f"
done

if [ ! -f "$CAMCONTROL_CONF" ]; then
    cp "$STAGE_DIR/camcontrol.conf" "$CAMCONTROL_CONF" || exit 1
    say "installed default configuration"
else
    say "kept existing configuration"
fi
chmod 600 "$CAMCONTROL_CONF"

. "$CAMCONTROL_DIR/bin/camcontrol-common.sh"

# A blank AP password would mean an open access point that anyone in range
# could use to rewrite the camera's credentials, so one is always generated.
if [ -z "$(cc_get ap_psk "")" ]; then
    # No `head` on this busybox build; dd bounds the urandom stream instead.
    generated=$(tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null |
        dd bs=1 count=14 2>/dev/null)
    if [ -z "$generated" ]; then
        generated=$(date +%s%N 2>/dev/null | md5sum 2>/dev/null | cut -c1-14)
    fi
    if [ -n "$generated" ]; then
        cc_set ap_psk "$generated"
        say "generated an access point password"
    else
        say "WARNING: could not generate an AP password; set ap_psk manually"
    fi
fi

if [ -z "$(cc_get ap_ssid "")" ]; then
    cc_set ap_ssid "camcontrol-$(cc_mac_suffix)"
fi

hook_installed=no
for candidate in $HOOK_CANDIDATES; do
    [ -f "$candidate" ] || continue
    if grep -q "$HOOK_MARKER" "$candidate" 2>/dev/null; then
        say "boot hook already present in $candidate"
        hook_installed=yes
        break
    fi
    cp "$candidate" "$candidate.camcontrol-backup" 2>/dev/null
    if printf '%s\n%s\n' "$HOOK_MARKER" \
        "[ -x $CAMCONTROL_DIR/bin/camcontrol-boot.sh ] && sh $CAMCONTROL_DIR/bin/camcontrol-boot.sh &" \
        >>"$candidate" 2>/dev/null; then
        say "boot hook added to $candidate (backup: $candidate.camcontrol-backup)"
        hook_installed=yes
        break
    fi
done

if [ "$hook_installed" != yes ]; then
    say "WARNING: no writable startup script found."
    say "         run camcontrol-boot.sh manually or add the hook yourself:"
    say "         sh $CAMCONTROL_DIR/bin/camcontrol-boot.sh &"
fi

say "--- capability probe ---"
for tool in dropbear wpa_supplicant wpa_cli nc base64 ifconfig wget chpasswd; do
    if cc_has "$tool"; then
        say "  $tool: present"
    else
        say "  $tool: MISSING"
    fi
done
say "  wifi interface: $(cc_wifi_iface)"
say "  ap ssid: $(cc_get ap_ssid "")"
say "install complete"
