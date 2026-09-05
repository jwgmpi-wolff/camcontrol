import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import 'camera_edit_screen.dart';
import 'discovery_screen.dart';
import 'storage_settings_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _urlCtrl;
  late TextEditingController _keyCtrl;
  bool _obscureKey = true;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    _urlCtrl = TextEditingController(text: state.baseUrl);
    _keyCtrl = TextEditingController(text: state.apiKey);
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    _keyCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await context.read<AppState>().saveSettings(
          _urlCtrl.text.trim(),
          _keyCtrl.text.trim(),
        );
    setState(() => _saved = true);
    await Future<void>.delayed(const Duration(seconds: 2));
    if (mounted) setState(() => _saved = false);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Gateway connection',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          TextField(
            controller: _urlCtrl,
            decoration: const InputDecoration(
              labelText: 'Gateway URL',
              hintText: 'http://192.168.1.x:8080',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.link),
            ),
            keyboardType: TextInputType.url,
            autocorrect: false,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _keyCtrl,
            obscureText: _obscureKey,
            decoration: InputDecoration(
              labelText: 'API Key (optional)',
              hintText: 'Leave blank if API_KEY is not set',
              border: const OutlineInputBorder(),
              prefixIcon: const Icon(Icons.key),
              suffixIcon: IconButton(
                icon: Icon(
                    _obscureKey ? Icons.visibility : Icons.visibility_off),
                onPressed: () => setState(() => _obscureKey = !_obscureKey),
              ),
            ),
            autocorrect: false,
          ),
          const SizedBox(height: 8),
          const Text(
            'The API key must match API_KEY on the gateway. '
            'Store it securely and rotate regularly.',
            style: TextStyle(fontSize: 12),
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            icon: Icon(_saved ? Icons.check : Icons.save),
            label: Text(_saved ? 'Saved' : 'Save'),
            onPressed: _save,
          ),
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Cameras', style: Theme.of(context).textTheme.titleMedium),
              Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.wifi_find),
                    tooltip: 'Discover cameras on network',
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const DiscoveryScreen()),
                    ).then((_) => state.refreshCameras()),
                  ),
                  IconButton(
                    icon: const Icon(Icons.add),
                    tooltip: 'Add camera',
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const CameraEditScreen()),
                    ).then((_) => state.refreshCameras()),
                  ),
                ],
              ),
            ],
          ),
          if (state.cameras.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text('No cameras configured yet.'),
            ),
          for (final camera in state.cameras)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.videocam),
              title: Text(camera.name),
              subtitle: Text(camera.type),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => CameraEditScreen(existing: camera),
                ),
              ).then((_) => state.refreshCameras()),
            ),
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 12),
          Text('Storage', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text(
            'Where captured images and videos are uploaded. Self-hosted '
            'options only — no YI or other commercial cloud service.',
            style: TextStyle(fontSize: 12),
          ),
          const SizedBox(height: 12),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.cloud),
            label: const Text('Configure storage provider'),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const StorageSettingsScreen()),
            ),
          ),
        ],
      ),
    );
  }
}
