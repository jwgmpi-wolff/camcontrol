import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../models/camera.dart';
import 'camera_edit_screen.dart';

/// Scans the local network for candidate cameras (open SSH/HTTP/RTSP ports)
/// so the user doesn't have to type IP addresses in by hand.
class DiscoveryScreen extends StatefulWidget {
  const DiscoveryScreen({super.key});

  @override
  State<DiscoveryScreen> createState() => _DiscoveryScreenState();
}

class _DiscoveryScreenState extends State<DiscoveryScreen> {
  bool _scanning = false;
  String? _error;
  List<DiscoveredCamera> _results = [];

  Future<void> _scan() async {
    setState(() { _scanning = true; _error = null; _results = []; });
    try {
      final results = await context.read<AppState>().api.discoverCameras();
      setState(() => _results = results);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _scanning = false);
    }
  }

  @override
  void initState() {
    super.initState();
    _scan();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Discover cameras'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _scanning ? null : _scan,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_scanning) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Scanning local network...'),
          ],
        ),
      );
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Text(_error!, textAlign: TextAlign.center),
        ),
      );
    }
    if (_results.isEmpty) {
      return const Center(
        child: Text('No candidate cameras found on the local network.'),
      );
    }
    return ListView.builder(
      itemCount: _results.length,
      itemBuilder: (context, i) {
        final result = _results[i];
        final recognized = result.suggestedType != 'unknown';
        return ListTile(
          leading: Icon(
            recognized ? Icons.videocam : Icons.help_outline,
            color: recognized ? Colors.green : null,
          ),
          title: Text(result.ip),
          subtitle: Text(
            '${result.fingerprint}\nOpen ports: ${result.openPorts.join(', ')}',
          ),
          isThreeLine: true,
          trailing: const Icon(Icons.chevron_right),
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => CameraEditScreen(
                prefillType: result.suggestedType == 'unknown'
                    ? 'yi_hack_v3_ssh'
                    : result.suggestedType,
                prefillHost: result.ip,
              ),
            ),
          ),
        );
      },
    );
  }
}
