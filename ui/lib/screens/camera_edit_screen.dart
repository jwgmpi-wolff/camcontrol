import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../main.dart';
import '../models/camera.dart';

/// Add or edit a single camera. Existing cameras are fetched from
/// /api/config (which redacts stored passwords), so editing any field other
/// than the password preserves it — the password field itself is left blank
/// and must be re-entered to change or keep it (no secret round-tripping).
class CameraEditScreen extends StatefulWidget {
  const CameraEditScreen({
    super.key,
    this.existing,
    this.prefillType,
    this.prefillHost,
  });

  final Camera? existing;
  final String? prefillType;
  final String? prefillHost;

  @override
  State<CameraEditScreen> createState() => _CameraEditScreenState();
}

class _CameraEditScreenState extends State<CameraEditScreen> {
  final _formKey = GlobalKey<FormState>();
  String _type = 'hi3518e_ssh';
  bool _loading = true;
  bool _saving = false;
  String? _error;

  final _idCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _hostCtrl = TextEditingController();
  final _portCtrl = TextEditingController(text: '22');
  final _usernameCtrl = TextEditingController(text: 'root');
  final _passwordCtrl = TextEditingController();
  final _remoteViewCtrl = TextEditingController(text: '/tmp/view');
  final _remoteMediaCtrl = TextEditingController(text: '/tmp/sd');
  final _rtspUrlCtrl = TextEditingController();
  bool _liveViewEnabled = false;
  final _liveViewIntervalCtrl = TextEditingController(text: '3');
  final _liveViewPublicUrlCtrl = TextEditingController();
  Map<String, dynamic>? _existingMotion;

  List<Map<String, dynamic>> _allCameras = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AppState>().api;
    try {
      final config = await api.getConfig();
      _allCameras =
          (config['cameras'] as List).cast<Map<String, dynamic>>();
      if (widget.existing != null) {
        final match = _allCameras.firstWhere(
          (c) => c['id'] == widget.existing!.id,
          orElse: () => {},
        );
        if (match.isNotEmpty) {
          _type = match['type'] as String;
          _idCtrl.text = match['id'] as String;
          _nameCtrl.text = match['name'] as String;
          if (_type == 'hi3518e_ssh') {
            _hostCtrl.text = match['host'] as String? ?? '';
            _portCtrl.text = '${match['port'] ?? 22}';
            _usernameCtrl.text = match['username'] as String? ?? 'root';
            _remoteViewCtrl.text = match['remote_view_path'] as String? ?? '/tmp/view';
            _remoteMediaCtrl.text = match['remote_media_dir'] as String? ?? '/tmp/sd';
            _existingMotion = match['motion'] as Map<String, dynamic>?;
            final liveView = match['live_view'] as Map<String, dynamic>?;
            _liveViewEnabled = liveView?['enabled'] as bool? ?? false;
            _liveViewIntervalCtrl.text =
                '${liveView?['poll_interval_seconds'] ?? 3}';
            _liveViewPublicUrlCtrl.text =
                liveView?['public_url'] as String? ?? '';
          } else {
            _rtspUrlCtrl.text = match['rtsp_url'] as String? ?? '';
          }
        }
      }
    } catch (e) {
      _error = 'Could not load existing config: $e';
    }
    if (widget.existing == null) {
      if (widget.prefillType != null) _type = widget.prefillType!;
      if (widget.prefillHost != null) {
        _hostCtrl.text = widget.prefillHost!;
        _idCtrl.text = widget.prefillHost!.replaceAll('.', '-');
        _nameCtrl.text = 'Camera ${widget.prefillHost}';
      }
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  void dispose() {
    _idCtrl.dispose();
    _nameCtrl.dispose();
    _hostCtrl.dispose();
    _portCtrl.dispose();
    _usernameCtrl.dispose();
    _passwordCtrl.dispose();
    _remoteViewCtrl.dispose();
    _remoteMediaCtrl.dispose();
    _rtspUrlCtrl.dispose();
    _liveViewIntervalCtrl.dispose();
    _liveViewPublicUrlCtrl.dispose();
    super.dispose();
  }

  Map<String, dynamic> _buildEntry() {
    if (_type == 'hi3518e_ssh') {
      final existingPassword = widget.existing != null
          ? (_allCameras.firstWhere(
                (c) => c['id'] == widget.existing!.id,
                orElse: () => {},
              )['password'] as String? ??
              '')
          : '';
      return {
        'type': 'hi3518e_ssh',
        'id': _idCtrl.text.trim(),
        'name': _nameCtrl.text.trim(),
        'host': _hostCtrl.text.trim(),
        'port': int.tryParse(_portCtrl.text.trim()) ?? 22,
        'username': _usernameCtrl.text.trim(),
        // Blank means "keep existing" only if that existing value wasn't
        // redacted (i.e. it was already blank server-side); a real stored
        // password must be re-entered here to preserve it.
        'password': _passwordCtrl.text.isNotEmpty
            ? _passwordCtrl.text
            : existingPassword,
        'remote_view_path': _remoteViewCtrl.text.trim(),
        'remote_media_dir': _remoteMediaCtrl.text.trim(),
        if (_existingMotion != null) 'motion': _existingMotion,
        'live_view': {
          'enabled': _liveViewEnabled,
          'poll_interval_seconds':
              double.tryParse(_liveViewIntervalCtrl.text.trim()) ?? 3.0,
          'public_url': _liveViewPublicUrlCtrl.text.trim(),
        },
      };
    }
    return {
      'type': 'rtsp',
      'id': _idCtrl.text.trim(),
      'name': _nameCtrl.text.trim(),
      'rtsp_url': _rtspUrlCtrl.text.trim(),
    };
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _saving = true; _error = null; });
    try {
      final entry = _buildEntry();
      final updated = [
        for (final c in _allCameras)
          if (c['id'] != entry['id']) c,
        entry,
      ];
      await context.read<AppState>().api.setCameras(updated);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _delete() async {
    setState(() { _saving = true; _error = null; });
    try {
      final updated = [
        for (final c in _allCameras)
          if (c['id'] != widget.existing!.id) c,
      ];
      await context.read<AppState>().api.setCameras(updated);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.existing == null ? 'Add camera' : 'Edit camera'),
        actions: [
          if (widget.existing != null)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: _saving ? null : _delete,
            ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (_error != null) ...[
              Text(_error!, style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 12),
            ],
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(
                  value: 'hi3518e_ssh',
                  label: Text('Hi3518e custom firmware (SSH)'),
                ),
                ButtonSegment(value: 'rtsp', label: Text('RTSP')),
              ],
              selected: {_type},
              onSelectionChanged: widget.existing == null
                  ? (s) => setState(() => _type = s.first)
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _idCtrl,
              enabled: widget.existing == null,
              decoration: const InputDecoration(
                labelText: 'Camera ID (unique, no spaces)',
                border: OutlineInputBorder(),
              ),
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Required' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _nameCtrl,
              decoration: const InputDecoration(
                labelText: 'Display name',
                border: OutlineInputBorder(),
              ),
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Required' : null,
            ),
            const SizedBox(height: 12),
            if (_type == 'hi3518e_ssh') ..._buildSshFields(),
            if (_type == 'rtsp') ..._buildRtspFields(),
            const SizedBox(height: 24),
            FilledButton.icon(
              icon: _saving
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save),
              label: const Text('Save'),
              onPressed: _saving ? null : _save,
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildSshFields() {
    return [
      TextFormField(
        controller: _hostCtrl,
        decoration: const InputDecoration(
          labelText: 'Host / IP address',
          border: OutlineInputBorder(),
        ),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _portCtrl,
        decoration: const InputDecoration(
          labelText: 'SSH port',
          border: OutlineInputBorder(),
        ),
        keyboardType: TextInputType.number,
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _usernameCtrl,
        decoration: const InputDecoration(
          labelText: 'Username',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _passwordCtrl,
        obscureText: true,
        decoration: const InputDecoration(
          labelText: 'Password',
          hintText: 'Leave blank to keep the existing password unchanged',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _remoteViewCtrl,
        decoration: const InputDecoration(
          labelText: 'Remote live-view buffer path',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _remoteMediaCtrl,
        decoration: const InputDecoration(
          labelText: 'Remote SD-card media directory',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 20),
      const Divider(),
      const SizedBox(height: 8),
      Text('Live view (direct from camera)',
          style: Theme.of(context).textTheme.titleSmall),
      const Text(
        'Publishes a refreshing snapshot to the camera\'s own web server '
        'at http://<camera-ip>/live.html, viewable without the app/gateway.',
        style: TextStyle(fontSize: 12),
      ),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('Enable live view'),
        value: _liveViewEnabled,
        onChanged: (v) => setState(() => _liveViewEnabled = v),
      ),
      TextFormField(
        controller: _liveViewIntervalCtrl,
        enabled: _liveViewEnabled,
        decoration: const InputDecoration(
          labelText: 'Refresh interval (seconds)',
          border: OutlineInputBorder(),
        ),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _liveViewPublicUrlCtrl,
        enabled: _liveViewEnabled,
        decoration: const InputDecoration(
          labelText: 'Public URL / DDNS (optional)',
          hintText: 'myhome.duckdns.org:8080',
          helperText: 'For viewing over the internet via a port-forwarded '
              'router. Leave blank to use the LAN IP.',
          border: OutlineInputBorder(),
        ),
        keyboardType: TextInputType.url,
        autocorrect: false,
      ),
      if (widget.existing != null) ...[
        const SizedBox(height: 12),
        OutlinedButton.icon(
          icon: const Icon(Icons.open_in_new),
          label: const Text('View live feed'),
          onPressed: () => _openLiveView(widget.existing!.id),
        ),
      ],
    ];
  }

  Future<void> _openLiveView(String cameraId) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final status =
          await context.read<AppState>().api.getLiveViewStatus(cameraId);
      final url = status['url'] as String?;
      if (url == null) {
        messenger.showSnackBar(
          const SnackBar(content: Text('Live view is not enabled for this camera')),
        );
        return;
      }
      final uri = Uri.parse(url);
      final launched =
          await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched) {
        messenger.showSnackBar(SnackBar(content: Text('Could not open $url')));
      }
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  List<Widget> _buildRtspFields() {
    return [
      TextFormField(
        controller: _rtspUrlCtrl,
        decoration: const InputDecoration(
          labelText: 'RTSP URL',
          hintText: 'rtsp://user:pass@camera-ip/stream',
          border: OutlineInputBorder(),
        ),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
    ];
  }
}
