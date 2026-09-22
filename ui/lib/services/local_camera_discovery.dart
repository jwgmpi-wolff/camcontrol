import 'dart:async';
import 'dart:io';

import '../models/camera.dart';

class LocalCameraDiscovery {
  static const _ports = [80, 22];
  static const _concurrency = 48;

  bool _isPrivate(InterfaceAddress address) {
    final octets = address.address.split('.').map(int.tryParse).toList();
    if (octets.length != 4 || octets.any((octet) => octet == null)) return false;
    return octets[0] == 10 ||
        (octets[0] == 172 && octets[1]! >= 16 && octets[1]! <= 31) ||
        (octets[0] == 192 && octets[1] == 168);
  }

  Future<List<DiscoveredCamera>> scan() async {
    final interfaces = await NetworkInterface.list(
      type: InternetAddressType.IPv4,
      includeLoopback: false,
      includeLinkLocal: false,
    );
    InternetAddress? localAddress;
    for (final interface in interfaces) {
      for (final address in interface.addresses) {
        if (_isPrivate(address)) {
          localAddress = address;
          break;
        }
      }
      if (localAddress != null) break;
    }
    if (localAddress == null) return [];

    final octets = localAddress.address.split('.');
    if (octets.length != 4) return [];
    final prefix = '${octets[0]}.${octets[1]}.${octets[2]}';
    final results = <DiscoveredCamera>[];
    final pending = <Future<void>>[];
    for (var host = 1; host < 255; host++) {
      final ip = '$prefix.$host';
      if (ip == localAddress.address) continue;
      pending.add(_probe(ip).then((result) {
        if (result != null) results.add(result);
      }));
      if (pending.length >= _concurrency) {
        await Future.wait(pending);
        pending.clear();
      }
    }
    await Future.wait(pending);
    results.sort((left, right) => left.ip.compareTo(right.ip));
    return results;
  }

  Future<DiscoveredCamera?> _probe(String ip) async {
    final openPorts = <int>[];
    for (final port in _ports) {
      try {
        final socket = await Socket.connect(
          ip,
          port,
          timeout: const Duration(milliseconds: 350),
        );
        await socket.close();
        openPorts.add(port);
      } on SocketException {
        // Closed ports are expected while scanning a local subnet.
      } on TimeoutException {
        // Unresponsive hosts are not camera candidates for this quick scan.
      }
    }
    if (!openPorts.contains(80)) return null;
    final isYiHackCandidate = openPorts.contains(22);
    return DiscoveredCamera(
      ip: ip,
      openPorts: openPorts,
      suggestedType: isYiHackCandidate ? 'hi3518e_ssh' : 'unknown',
      suggestedName: isYiHackCandidate ? 'Yi camera $ip' : 'Camera $ip',
      fingerprint: isYiHackCandidate
          ? 'HTTP and SSH available on local network'
          : 'HTTP server available on local network',
    );
  }
}
