import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';

class StreamScreen extends StatefulWidget {
  const StreamScreen({super.key});

  @override
  State<StreamScreen> createState() => _StreamScreenState();
}

class _StreamScreenState extends State<StreamScreen>
    with WidgetsBindingObserver {
  Timer? _timer;
  Uint8List? _frame;
  bool _active = false;
  String? _error;
  int _fps = 0;
  int _frameCount = 0;
  DateTime _fpsWindow = DateTime.now();

  void _startPolling() {
    _active = true;
    // Poll at 100 ms → ~10 fps; camera latency determines actual rate
    _timer = Timer.periodic(const Duration(milliseconds: 100), (_) => _poll());
  }

  void _stopPolling() {
    _active = false;
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _poll() async {
    if (!mounted) return;
    try {
      final api = context.read<AppState>().api;
      final bytes = await api.fetchFrame();
      _frameCount++;
      final now = DateTime.now();
      if (now.difference(_fpsWindow).inSeconds >= 1) {
        _fps = _frameCount;
        _frameCount = 0;
        _fpsWindow = now;
      }
      if (mounted) setState(() { _frame = bytes; _error = null; });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
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
    if (state == AppLifecycleState.resumed && !_active) _startPolling();
  }

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Live View'),
        actions: [
          if (_frame != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Center(child: Text('$_fps fps')),
            ),
          IconButton(
            icon: Icon(
              appState.recording ? Icons.stop_circle : Icons.fiber_manual_record,
              color: appState.recording ? Colors.red : null,
            ),
            tooltip:
                appState.recording ? 'Stop Recording' : 'Start Recording',
            onPressed: () async {
              try {
                if (appState.recording) {
                  await appState.api.stopRecording();
                } else {
                  await appState.api.startRecording();
                }
                await appState.refresh();
              } catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(context)
                      .showSnackBar(SnackBar(content: Text(e.toString())));
                }
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.photo_camera),
            tooltip: 'Snapshot',
            onPressed: () async {
              try {
                final r = await appState.api.snapshot();
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Saved: ${r['path']}')),
                  );
                }
              } catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(context)
                      .showSnackBar(SnackBar(content: Text(e.toString())));
                }
              }
            },
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_error != null && _frame == null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.videocam_off, size: 64),
            const SizedBox(height: 16),
            Text(_error!, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            const Text(
              'Ensure the gateway is running and the camera is connected.',
              textAlign: TextAlign.center,
            ),
          ],
        ),
      );
    }
    if (_frame == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        Image.memory(
          _frame!,
          gaplessPlayback: true, // prevents flicker between frames
          fit: BoxFit.contain,
        ),
        if (context.watch<AppState>().recording)
          const Positioned(
            top: 12,
            right: 12,
            child: _RecordingBadge(),
          ),
      ],
    );
  }
}

class _RecordingBadge extends StatefulWidget {
  const _RecordingBadge();

  @override
  State<_RecordingBadge> createState() => _RecordingBadgeState();
}

class _RecordingBadgeState extends State<_RecordingBadge>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _ctrl,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.red,
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.fiber_manual_record, color: Colors.white, size: 12),
            SizedBox(width: 4),
            Text('REC', style: TextStyle(color: Colors.white, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}
