import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../models/camera.dart';
import '../utils/feed_health_monitor.dart';
import '../widgets/feed_health_indicator.dart';

/// A single camera's live-polling preview tile, used inside the multi-view
/// grid. Each tile polls independently at a rate suited to its camera type.
class CameraTile extends StatefulWidget {
  const CameraTile({super.key, required this.camera});

  final Camera camera;

  @override
  State<CameraTile> createState() => _CameraTileState();
}

class _CameraTileState extends State<CameraTile> with WidgetsBindingObserver {
  static const _audioChannel = MethodChannel('camcontrol/audio');

  Timer? _timer;
  Uint8List? _frame;
  String? _error;
  bool _fetching = false;
  bool _recording = false;
  bool _busy = false;
  late final FeedHealthMonitor _health;
  bool _talking = false;
  Timer? _talkTimer;

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
    if (!mounted) return;
    if (_fetching) {
      setState(() {});
      return;
    }
    _fetching = true;
    try {
      final api = context.read<AppState>().api;
      final bytes = await api.fetchSnapshot(widget.camera.id);
      if (mounted) {
        _health.recordFrame(bytes);
        setState(() {
          _frame = bytes;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) {
        _health.recordFailure();
        setState(() => _error = e.toString());
      }
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
        messenger.showSnackBar(
          const SnackBar(content: Text('Recording stopped')),
        );
      } else {
        await api.startRecording(widget.camera.id);
        messenger.showSnackBar(
          const SnackBar(content: Text('Recording started')),
        );
      }
      if (mounted) setState(() => _recording = !_recording);
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Recording failed: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggleTalk() async {
    if (_busy) return;
    if (_talking) {
      await _sendVoiceMessage();
      return;
    }

    final messenger = ScaffoldMessenger.of(context);
    final permitted =
        await _audioChannel.invokeMethod<bool>('requestPermission') ?? false;
    if (!permitted) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Microphone permission is required')),
      );
      return;
    }

    try {
      await _audioChannel.invokeMethod<String>('start');
      if (!mounted) return;
      setState(() => _talking = true);
      _talkTimer = Timer(const Duration(seconds: 30), _sendVoiceMessage);
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('Could not start microphone: $e')),
      );
    }
  }

  Future<void> _sendVoiceMessage() async {
    if (!_talking) return;
    _talkTimer?.cancel();
    _talkTimer = null;
    setState(() {
      _talking = false;
      _busy = true;
    });
    final messenger = ScaffoldMessenger.of(context);
    final api = context.read<AppState>().api;
    try {
      final path = await _audioChannel.invokeMethod<String>('stop');
      if (path == null) throw StateError('No audio was recorded');
      final file = File(path);
      final audio = await file.readAsBytes();
      await api.playVoiceMessage(widget.camera.id, audio);
      await file.delete().catchError((_) => file);
      messenger.showSnackBar(
        const SnackBar(content: Text('Voice message played on camera')),
      );
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('Voice message failed: $e')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void initState() {
    super.initState();
    _health = FeedHealthMonitor.forPollInterval(_pollInterval(context));
    WidgetsBinding.instance.addObserver(this);
    _startPolling();
  }

  @override
  void dispose() {
    _stopPolling();
    _talkTimer?.cancel();
    if (_talking) unawaited(_audioChannel.invokeMethod<String>('stop'));
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) _stopPolling();
    if (state == AppLifecycleState.resumed && _timer == null) {
      _health.resume();
      _startPolling();
    }
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
                if (widget.camera.type == 'hi3518e_ssh')
                  IconButton(
                    icon: Icon(
                      _talking ? Icons.stop_circle : Icons.mic,
                      size: 18,
                      color: _talking ? Colors.red : null,
                    ),
                    tooltip: _talking
                        ? 'Stop and play voice message'
                        : 'Talk through camera speaker',
                    visualDensity: VisualDensity.compact,
                    onPressed: _busy ? null : _toggleTalk,
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
                FeedHealthIndicator(
                  health: _isLiveViewUnavailable
                      ? FeedHealth.connecting
                      : _health.status(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildImage() {
    final health = _health.status();
    if (_frame != null && health != FeedHealth.live) {
      return FeedUnavailable(health: health, detail: _error);
    }
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
