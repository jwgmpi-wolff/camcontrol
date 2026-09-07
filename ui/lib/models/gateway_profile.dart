/// A named gateway connection (e.g. "Local" on the LAN, "Azure" for a
/// cloud-hosted deployment). Users can add/switch between multiple profiles
/// without losing each one's settings.
class GatewayProfile {
  GatewayProfile({
    required this.name,
    required this.baseUrl,
    this.apiKey = '',
    this.username = '',
    this.token = '',
  });

  String name;
  String baseUrl;
  String apiKey;
  String username;
  String token;

  Map<String, dynamic> toJson() => {
        'name': name,
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'username': username,
        'token': token,
      };

  factory GatewayProfile.fromJson(Map<String, dynamic> json) => GatewayProfile(
        name: json['name'] as String,
        baseUrl: json['baseUrl'] as String,
        apiKey: json['apiKey'] as String? ?? '',
        username: json['username'] as String? ?? '',
        token: json['token'] as String? ?? '',
      );
}
