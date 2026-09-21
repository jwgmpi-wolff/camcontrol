import 'dart:convert';

/// Builds the YI onboarding QR payload used by YI cameras. SSID and password
/// are base64-encoded UTF-8 strings; the pairing key is supplied by YI during
/// device onboarding when the camera requires one.
String buildYiWifiQrPayload({
  required String ssid,
  required String password,
  String bindKey = '',
}) {
  final fields = <String>[];
  if (bindKey.trim().isNotEmpty) fields.add('b=${bindKey.trim()}');
  fields.add('s=${base64Encode(utf8.encode(ssid))}');
  fields.add('p=${base64Encode(utf8.encode(password))}');
  return fields.join('&');
}
