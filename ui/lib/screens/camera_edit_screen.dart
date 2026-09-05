import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

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
  String _type = 'yi_hack_v3_ssh';
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
          if (_type == 'yi_hack_v3_ssh') {
            _hostCtrl.text = match['host'] as String? ?? '';
            _portCtrl.text = '${match['port'] ?? 22}';
            _usernameCtrl.text = match['username'] as String? ?? 'root';
            _remoteViewCtrl.text = match['remote_view_path'] as String? ?? '/tmp/view';
            _remoteMediaCtrl.text = match['remote_media_dir'] as String? ?? '/tmp/sd';
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
    super.dispose();
  }

  Map<String, dynamic> _buildEntry() {
    if (_type == 'yi_hack_v3_ssh') {
      final existingPassword = widget.existing != null
          ? (_allCameras.firstWhere(
                (c) => c['id'] == widget.existing!.id,
                orElse: () => {},
              )['password'] as String? ??
              '')
          : '';
      return {
        'type': 'yi_hack_v3_ssh',
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
                  value: 'yi_hack_v3_ssh',
                  label: Text('yi-hack-v3 (SSH)'),
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
            if (_type == 'yi_hack_v3_ssh') ..._buildSshFields(),
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
    ];
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
