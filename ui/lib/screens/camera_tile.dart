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

  void _startPolling() {
    _poll();
    _timer = Timer.periodic(widget.camera.recommendedPollInterval, (_) => _poll());
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
