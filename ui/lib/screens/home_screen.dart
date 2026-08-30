import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppState>().refresh();
    });
  }

  Future<void> _act(Future<void> Function() fn) async {
    setState(() => _loading = true);
    try {
      await fn();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.toString())));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('CamControl'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _act(state.refresh),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _StatusCard(state: state),
                const SizedBox(height: 16),
                _DeviceCard(state: state),
                const SizedBox(height: 16),
                _ActionGrid(state: state, onAct: _act),
              ],
            ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final ok = state.status != 'unreachable';
    return Card(
      child: ListTile(
        leading: Icon(
          ok ? Icons.check_circle : Icons.error,
          color: ok ? Colors.green : Colors.red,
        ),
        title: Text(ok ? 'Gateway online' : 'Gateway unreachable'),
        subtitle: Text(state.baseUrl),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (state.streaming)
              const Chip(label: Text('STREAM'), padding: EdgeInsets.zero),
            if (state.recording)
              const Chip(label: Text('REC ●'), padding: EdgeInsets.zero),
          ],
        ),
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final d = state.device;
    if (d.isEmpty) {
      return OutlinedButton.icon(
        icon: const Icon(Icons.camera_alt),
        label: const Text('Load camera info'),
        onPressed: () async {
          try {
            await context.read<AppState>().fetchDevice();
          } catch (e) {
            if (context.mounted) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(SnackBar(content: Text(e.toString())));
            }
          }
        },
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Camera', style: Theme.of(context).textTheme.labelSmall),
            const SizedBox(height: 4),
            Text(
              d['name'] as String? ?? d['device_path'] as String? ?? '—',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if ((d['usb_metadata'] as Map?)?.isNotEmpty == true ||
                (d['known_profile'] as Map?)?.isNotEmpty == true) ...[
              const SizedBox(height: 8),
              const Divider(),
              for (final entry in {
                ...?(d['usb_metadata'] as Map?)?.cast<String, dynamic>(),
                ...?(d['known_profile'] as Map?)?.cast<String, dynamic>(),
              }.entries)
                Text('${entry.key}: ${entry.value}',
                    style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

class _ActionGrid extends StatelessWidget {
  const _ActionGrid({required this.state, required this.onAct});
  final AppState state;
  final Future<void> Function(Future<void> Function()) onAct;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        _ActionButton(
          icon: state.streaming ? Icons.stop : Icons.play_arrow,
          label: state.streaming ? 'Stop Stream' : 'Start Stream',
          onPressed: () => onAct(() async {
            if (state.streaming) {
              await state.api.stopStream();
            } else {
              await state.api.startStream();
            }
            await state.refresh();
          }),
        ),
        _ActionButton(
          icon: state.recording ? Icons.stop_circle : Icons.fiber_manual_record,
          label: state.recording ? 'Stop Recording' : 'Start Recording',
          color: state.recording ? Colors.red : null,
          onPressed: () => onAct(() async {
            if (state.recording) {
              await state.api.stopRecording();
            } else {
              await state.api.startRecording();
            }
            await state.refresh();
          }),
        ),
        _ActionButton(
          icon: Icons.photo_camera,
          label: 'Snapshot',
          onPressed: () => onAct(() async {
            final r = await state.api.snapshot();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Saved: ${r['path']}')),
              );
            }
          }),
        ),
      ],
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onPressed,
    this.color,
  });
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      icon: Icon(icon, color: color),
      label: Text(label),
      onPressed: onPressed,
      style: color != null
          ? FilledButton.styleFrom(backgroundColor: color)
          : null,
    );
  }
}
