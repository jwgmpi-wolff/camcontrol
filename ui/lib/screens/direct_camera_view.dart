import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../main.dart';
import '../models/direct_camera.dart';

/// Full-screen live view for one gateway-less "Direct camera". Polls the
/// camera's own `/live.jpg` (published by live_view_publisher.py) straight
/// over HTTP -- no camera_bridge gateway involved at all.
class DirectCameraView extends StatefulWidget {
  const DirectCameraView({super.key, required this.camera});

  final DirectCamera camera;

  @override
  State<DirectCameraView> createState() => _DirectCameraViewState();
}

class _DirectCameraViewState extends State<DirectCameraView>
    with WidgetsBindingObserver {
  Timer? _timer;
  Uint8List? _frame;
  String? _error;
  bool _fetching = false;

  // Users often paste a full browser URL (e.g. "10.0.0.252/live.html") --
  // extract just the host[:port] regardless of scheme/path they included.
  String get _normalizedHost {
    final input = widget.camera.host.trim();
    if (input.isEmpty) return '';
    final uri = Uri.tryParse(input.contains('://') ? input : 'http://$input');
    if (uri == null || uri.host.isEmpty) return input;
    return uri.hasPort ? '${uri.host}:${uri.port}' : uri.host;
  }

  Duration get _pollInterval {
    final override = context.read<AppState>().pollIntervalSeconds;
    return Duration(seconds: override > 0 ? override : 3);
  }

  void _startPolling() {
    _poll();
    _timer = Timer.periodic(_pollInterval, (_) => _poll());
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _poll() async {
    if (_fetching || !mounted) return;
    final host = _normalizedHost;
    if (host.isEmpty) {
      setState(() {
        _error = 'No camera address configured';
        _frame = null;
      });
      return;
    }
    _fetching = true;
    try {
      final res = await http
          .get(Uri.parse('http://$host/live.jpg?t=${DateTime.now().millisecondsSinceEpoch}'))
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) {
        throw Exception('HTTP ${res.statusCode}');
      }
      if (mounted) setState(() { _frame = res.bodyBytes; _error = null; });
    } catch (e) {
      if (mounted) setState(() => _error = 'Unreachable: $e');
    } finally {
      _fetching = false;
    }
  }

  Future<void> _openInBrowser() async {
    final messenger = ScaffoldMessenger.of(context);
    final host = _normalizedHost;
    if (host.isEmpty) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Set a camera address in Settings first')),
      );
      return;
    }
    final uri = Uri.parse('http://$host/live.html');
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!launched && mounted) {
      messenger.showSnackBar(SnackBar(content: Text('Could not open $uri')));
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _startPolling();
  }

  @override
  void dispose() {
    _stopPolling();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) _stopPolling();
    if (state == AppLifecycleState.resumed && _timer == null) _startPolling();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.camera.name),
        actions: [
          IconButton(
            icon: const Icon(Icons.open_in_browser),
            tooltip: 'Open live.html in browser',
            onPressed: _openInBrowser,
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _poll,
          ),
        ],
      ),
      body: Center(child: _buildImage()),
    );
  }

  Widget _buildImage() {
    if (_frame == null && _error == null) {
      return const CircularProgressIndicator();
    }
    if (_frame == null) {
      return Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.videocam_off, size: 48, color: Colors.grey.shade500),
            const SizedBox(height: 12),
            Text(
              _error!,
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade400),
            ),
            const SizedBox(height: 8),
            const Text(
              'Check the camera address in Settings and that live view is '
              'enabled on that camera.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12),
            ),
          ],
        ),
      );
    }
    return InteractiveViewer(
      child: Image.memory(_frame!, gaplessPlayback: true),
    );
  }
}
