import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../models/camera.dart';

/// A single camera's live-polling preview tile, used inside the multi-view
/// grid. Each tile polls independently at a rate suited to its camera type.
class CameraTile extends StatefulWidget {
  const CameraTile({super.key, required this.camera});

  final Camera camera;

  @override
  State<CameraTile> createState() => _CameraTileState();
}

class _CameraTileState extends State<CameraTile> with WidgetsBindingObserver {
  Timer? _timer;
  Uint8List? _frame;
  String? _error;
  bool _fetching = false;
  bool _recording = false;
  bool _busy = false;

  Duration _pollInterval(BuildContext context) {
    final override = context.read<AppState>().pollIntervalSeconds;
    return override > 0
        ? Duration(seconds: override)
        : widget.camera.recommendedPollInterval;
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
    _fetching = true;
    try {
      final api = context.read<AppState>().api;
      final bytes = await api.fetchSnapshot(widget.camera.id);
      if (mounted) setState(() { _frame = bytes; _error = null; });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      _fetching = false;
    }
  }

  Future<void> _takeSnapshot() async {
    if (_busy) return;
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await context.read<AppState>().api.captureAndStore(widget.camera.id);
      messenger.showSnackBar(
        const SnackBar(content: Text('Snapshot saved to storage')),
      );
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Snapshot failed: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggleRecording() async {
    if (_busy) return;
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    final api = context.read<AppState>().api;
    try {
      if (_recording) {
        await api.stopRecording(widget.camera.id);
        messenger.showSnackBar(const SnackBar(content: Text('Recording stopped')));
      } else {
        await api.startRecording(widget.camera.id);
        messenger.showSnackBar(const SnackBar(content: Text('Recording started')));
      }
      if (mounted) setState(() => _recording = !_recording);
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Recording failed: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
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

  // Some camera types (the SSH mmap-scrape fallback) don't have a documented,
  // reliable live-view mechanism at all -- treat "no frame available yet" as
  // an expected soft state, not a connectivity failure.
  bool get _isLiveViewUnavailable =>
      _error?.contains('No decodable frame') ?? false;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
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
                  icon: const Icon(Icons.camera_alt, size: 18),
                  tooltip: 'Take snapshot',
                  visualDensity: VisualDensity.compact,
                  onPressed: _busy ? null : _takeSnapshot,
                ),
                IconButton(
                  icon: Icon(
                    _recording ? Icons.stop_circle : Icons.fiber_manual_record,
                    size: 18,
                    color: _recording ? Colors.red : null,
                  ),
                  tooltip: _recording ? 'Stop recording' : 'Start recording',
                  visualDensity: VisualDensity.compact,
                  onPressed: _busy ? null : _toggleRecording,
                ),
                Icon(
                  _error == null ? Icons.circle : Icons.error,
                  size: 10,
                  color: _error == null
                      ? Colors.green
                      : (_isLiveViewUnavailable ? Colors.grey : Colors.red),
                ),
              ],
            ),
          ),
        ],
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
    if (_frame == null && _isLiveViewUnavailable) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.videocam_off, size: 28, color: Colors.grey.shade500),
              const SizedBox(height: 6),
              Text(
                'Live view unavailable\nSee Media tab for recordings',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 11, color: Colors.grey.shade400),
              ),
            ],
          ),
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
