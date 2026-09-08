/// A named gateway connection (e.g. "Local" on the LAN, "Azure" for a
/// cloud-hosted deployment) OR a direct, gateway-less connection straight to
/// a single camera's own IP/DDNS address. Users can add/switch between
/// multiple profiles without losing each one's settings.
class GatewayProfile {
  GatewayProfile({
    required this.name,
    required this.baseUrl,
    this.apiKey = '',
    this.username = '',
    this.token = '',
    this.mode = 'gateway',
    this.directHost = '',
  });

  String name;
  String baseUrl;
  String apiKey;
  String username;
  String token;

  /// 'gateway' (default, talks to the camera_bridge REST API) or 'direct'
  /// (talks straight to one camera's own web server, no gateway needed).
  String mode;

  /// Camera IP/DDNS host (optionally "host:port") used when [mode] is
  /// 'direct'. Ignored in 'gateway' mode.
  String directHost;

  bool get isDirect => mode == 'direct';

  Map<String, dynamic> toJson() => {
        'name': name,
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'username': username,
        'token': token,
        'mode': mode,
        'directHost': directHost,
      };

  factory GatewayProfile.fromJson(Map<String, dynamic> json) => GatewayProfile(
        name: json['name'] as String,
        baseUrl: json['baseUrl'] as String,
        apiKey: json['apiKey'] as String? ?? '',
        username: json['username'] as String? ?? '',
        token: json['token'] as String? ?? '',
        mode: json['mode'] as String? ?? 'gateway',
        directHost: json['directHost'] as String? ?? '',
      );
}
