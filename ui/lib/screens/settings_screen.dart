import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';

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
          Text('Camera', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const _InfoRow('Model', 'YI Outdoor Camera 1080p (YHS.3017)'),
          const _InfoRow('FCC ID', '2AFIB-YHS3017'),
          const _InfoRow('Manufacturer', 'Shanghai Xiaoyi Technology Co.,Ltd.'),
          const _InfoRow('Connection', 'WiFi / RTSP (local network)'),
          const _InfoRow('RTSP path hint', '/ch0_0.264  (port 554)'),
          const SizedBox(height: 12),
          const Text(
            'Set CAMERA_RTSP_URL=rtsp://<camera-ip>/ch0_0.264 in the gateway '
            '.env file. The gateway forwards the feed; no firmware changes are made.',
            style: TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 140,
            child: Text(label,
                style: const TextStyle(fontWeight: FontWeight.w500)),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
