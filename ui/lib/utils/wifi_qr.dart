/// Builds the standard `WIFI:` QR payload (read by Android/iOS camera apps)
/// for joining a Wi-Fi network. Special characters must be backslash-escaped
/// per the de-facto spec: `\`, `;`, `,`, `:`, and `"`.
String buildWifiQrPayload({
  required String ssid,
  required String password,
  required String security,
}) {
  final s = _escape(ssid);
  final p = _escape(password);
  if (security == 'nopass') {
    return 'WIFI:T:nopass;S:$s;;';
  }
  return 'WIFI:T:$security;S:$s;P:$p;;';
}

String _escape(String value) {
  return value
      .replaceAll(r'\', r'\\')
      .replaceAll(';', r'\;')
      .replaceAll(',', r'\,')
      .replaceAll(':', r'\:')
      .replaceAll('"', r'\"');
}
