import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import '../main.dart';
import '../models/direct_camera.dart';
import 'direct_camera_view.dart';

/// A single gateway-less camera's live-polling preview tile, used in the
/// direct-mode grid. Talks straight to the camera's own `/live.jpg`.
class DirectCameraTile extends StatefulWidget {
  const DirectCameraTile({super.key, required this.camera});

  final DirectCamera camera;

  @override
  State<DirectCameraTile> createState() => _DirectCameraTileState();
}

class _DirectCameraTileState extends State<DirectCameraTile>
    with WidgetsBindingObserver {
  http.Client _httpClient = http.Client();
  Timer? _timer;
  Uint8List? _frame;
  String? _error;
  bool _fetching = false;

  // Users often paste a full browser URL (e.g. "10.0.0.252/live.html") --
  // extract just the host[:port] regardless of scheme/path they included.
  String get _host {
    final input = widget.camera.host.trim();
    if (input.isEmpty) return '';
    final uri = Uri.tryParse(input.contains('://') ? input : 'http://$input');
    if (uri == null || uri.host.isEmpty) return input;
    return uri.hasPort ? '${uri.host}:${uri.port}' : uri.host;
  }

  Duration _pollInterval(BuildContext context) {
    final override = context.read<AppState>().pollIntervalSeconds;
    return Duration(seconds: override > 0 ? override : 3);
  }

  void _startPolling() {
    _poll();
    _timer = Timer.periodic(_pollInterval(context), (_) => _poll());
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _poll() async {
    if (_fetching || !mounted) return;
    final host = _host;
    if (host.isEmpty) {
      setState(() { _error = 'No address set'; _frame = null; });
      return;
    }
    _fetching = true;
    try {
      final res = await _httpClient
          .get(Uri.parse(
              'http://$host/live.jpg?t=${DateTime.now().millisecondsSinceEpoch}'))
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) throw Exception('HTTP ${res.statusCode}');
      if (mounted) setState(() { _frame = res.bodyBytes; _error = null; });
    } catch (e) {
      if (mounted) {
        _httpClient.close();
        _httpClient = http.Client();
        setState(() => _error = 'Unreachable');
      }
    } finally {
      _fetching = false;
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
    _httpClient.close();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) _stopPolling();
    if (state == AppLifecycleState.resumed && _timer == null) _startPolling();
  }

  Future<void> _showEditDialog() async {
    final nameCtrl = TextEditingController(text: widget.camera.name);
    final hostCtrl = TextEditingController(text: widget.camera.host);
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit camera'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: hostCtrl,
              decoration: const InputDecoration(
                labelText: 'Camera URL or address',
                hintText: 'http://192.168.1.50/live.html',
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, 'delete'),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, 'save'),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (!mounted || result == null) return;
    final state = context.read<AppState>();
    if (result == 'save') {
      await state.updateDirectCamera(
        widget.camera.id,
        name: nameCtrl.text.trim(),
        host: hostCtrl.text.trim(),
      );
    } else if (result == 'delete') {
      await state.removeDirectCamera(widget.camera.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => DirectCameraView(camera: widget.camera),
          ),
        ),
        child: Column(
          children: [
            Expanded(child: _buildImage()),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.camera.name,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.edit, size: 18),
                    tooltip: 'Edit / remove',
                    visualDensity: VisualDensity.compact,
                    onPressed: _showEditDialog,
                  ),
                  Icon(
                    _error == null ? Icons.circle : Icons.error,
                    size: 10,
                    color: _error == null ? Colors.green : Colors.red,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImage() {
    if (_frame == null && _error == null) {
      return const Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    if (_frame == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Text(
            _error!,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 11),
          ),
        ),
      );
    }
    return Image.memory(
      _frame!,
      fit: BoxFit.cover,
      width: double.infinity,
      gaplessPlayback: true,
    );
  }
}
