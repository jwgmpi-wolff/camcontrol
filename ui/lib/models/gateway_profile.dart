import 'direct_camera.dart';

/// A named gateway connection (e.g. "Local" on the LAN, "Azure" for a
/// cloud-hosted deployment) OR a direct, gateway-less connection straight to
/// one or more cameras' own IP/DDNS addresses. Users can add/switch between
/// multiple profiles without losing each one's settings.
class GatewayProfile {
  GatewayProfile({
    required this.name,
    required this.baseUrl,
    this.apiKey = '',
    this.username = '',
    this.token = '',
    this.mode = 'gateway',
    List<DirectCamera>? directCameras,
  }) : directCameras = directCameras ?? [];

  String name;
  String baseUrl;
  String apiKey;
  String username;
  String token;

  /// 'gateway' (default, talks to the camera_bridge REST API) or 'direct'
  /// (talks straight to one or more cameras' own web servers, no gateway
  /// needed).
  String mode;

  /// Cameras added directly by IP/DDNS. Only used when [mode] is 'direct'.
  List<DirectCamera> directCameras;

  bool get isDirect => mode == 'direct';

  Map<String, dynamic> toJson() => {
        'name': name,
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'username': username,
        'token': token,
        'mode': mode,
        'directCameras': directCameras.map((c) => c.toJson()).toList(),
      };

  factory GatewayProfile.fromJson(Map<String, dynamic> json) {
    var cameras = (json['directCameras'] as List<dynamic>?)
            ?.map((e) => DirectCamera.fromJson(e as Map<String, dynamic>))
            .toList() ??
        <DirectCamera>[];
    // Back-compat: older builds stored a single directHost string instead of
    // a list.
    final legacyHost = json['directHost'] as String?;
    if (cameras.isEmpty && legacyHost != null && legacyHost.isNotEmpty) {
      cameras = [
        DirectCamera(
          id: 'legacy',
          name: json['name'] as String? ?? 'Camera',
          host: legacyHost,
        ),
      ];
    }
    return GatewayProfile(
      name: json['name'] as String,
      baseUrl: json['baseUrl'] as String,
      apiKey: json['apiKey'] as String? ?? '',
      username: json['username'] as String? ?? '',
      token: json['token'] as String? ?? '',
      mode: json['mode'] as String? ?? 'gateway',
      directCameras: cameras,
    );
  }
}
