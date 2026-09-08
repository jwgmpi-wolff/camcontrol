/// A single camera reachable directly by IP/DDNS, bypassing the gateway.
class DirectCamera {
  DirectCamera({required this.id, required this.name, required this.host});

  String id;
  String name;
  String host;

  Map<String, dynamic> toJson() => {'id': id, 'name': name, 'host': host};

  factory DirectCamera.fromJson(Map<String, dynamic> json) => DirectCamera(
        id: json['id'] as String,
        name: json['name'] as String,
        host: json['host'] as String? ?? '',
      );
}
