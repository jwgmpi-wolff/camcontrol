class Camera {
  Camera({
    required this.id,
    required this.name,
    required this.type,
  });

  final String id;
  final String name;
  final String type; // "yi_hack_v3_ssh" | "rtsp"

  factory Camera.fromJson(Map<String, dynamic> json) => Camera(
        id: json['id'] as String,
        name: json['name'] as String,
        type: json['type'] as String,
      );

  /// Cameras without RTSP need a slower poll interval: the fallback
  /// mmap-scrape mechanism is a best-effort snapshot, not a live feed.
  Duration get recommendedPollInterval =>
      type == 'rtsp' ? const Duration(seconds: 1) : const Duration(seconds: 4);
}

class DiscoveredCamera {
  DiscoveredCamera({
    required this.ip,
    required this.openPorts,
    required this.suggestedType,
    required this.suggestedName,
    required this.fingerprint,
  });

  final String ip;
  final List<int> openPorts;
  final String suggestedType;
  final String suggestedName;
  final String fingerprint;

  factory DiscoveredCamera.fromJson(Map<String, dynamic> json) =>
      DiscoveredCamera(
        ip: json['ip'] as String,
        openPorts: (json['open_ports'] as List).cast<int>(),
        suggestedType: json['suggested_type'] as String,
        suggestedName: json['suggested_name'] as String,
        fingerprint: json['fingerprint'] as String,
      );
}

