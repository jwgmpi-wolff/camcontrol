/// Builds the `configure_wifi.cfg` contents used by yi-hack-family custom
/// firmware (SD-card Wi-Fi recovery method) to reset a hacked camera's SSID
/// and password without the vendor app. Field names (`ssid=`/`psk=`, no
/// quotes) follow the documented convention for this fork family, but the
/// exact fork/version running on a given camera hasn't been source-verified
/// here -- confirm against that camera's own SD-card template/instructions
/// before relying on this in an emergency.
///
/// Only these special characters are documented as supported in the ssid/psk
/// values (besides letters, digits, and spaces); anything else may not be
/// read correctly by the firmware's config parser.
const String allowedYiHackWifiSpecialChars = r'''\|!"$%&/()'?^[]@<>,;.:-_''';

String buildYiHackWifiConfig({required String ssid, required String password}) {
  return 'ssid=$ssid\npsk=$password\n';
}

/// Returns the characters in [value] that fall outside the documented
/// allowed set (letters, digits, spaces, and [allowedYiHackWifiSpecialChars]).
List<String> unsupportedYiHackWifiChars(String value) {
  final allowed = allowedYiHackWifiSpecialChars.split('').toSet();
  final bad = <String>{};
  for (final ch in value.split('')) {
    final isAlnum = RegExp(r'[a-zA-Z0-9 ]').hasMatch(ch);
    if (!isAlnum && !allowed.contains(ch)) {
      bad.add(ch);
    }
  }
  return bad.toList();
}
