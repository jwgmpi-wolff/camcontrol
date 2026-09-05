import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';

/// Storage provider is where captures/recordings get uploaded — entirely
/// self-hosted options, no YI or other commercial camera-cloud service.
/// Azure Blob Storage is listed first as the prioritized default.
class StorageSettingsScreen extends StatefulWidget {
  const StorageSettingsScreen({super.key});

  @override
  State<StorageSettingsScreen> createState() => _StorageSettingsScreenState();
}

class _StorageSettingsScreenState extends State<StorageSettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  String _provider = 'azure_blob';
  bool _loading = true;
  bool _saving = false;
  String? _error;

  // Azure Blob
  final _containerCtrl = TextEditingController(text: 'camcontrol');
  final _azurePrefixCtrl = TextEditingController(text: 'camcontrol/');
  final _connectionStringCtrl = TextEditingController();
  final _accountUrlCtrl = TextEditingController();

  // Local
  final _localPathCtrl = TextEditingController(text: './captures');

  // S3
  final _bucketCtrl = TextEditingController();
  final _s3PrefixCtrl = TextEditingController(text: 'camcontrol/');
  final _endpointCtrl = TextEditingController();
  final _regionCtrl = TextEditingController();
  final _accessKeyCtrl = TextEditingController();
  final _secretKeyCtrl = TextEditingController();

  // WebDAV
  final _baseUrlCtrl = TextEditingController();
  final _remoteDirCtrl = TextEditingController(text: 'camcontrol');
  final _webdavUserCtrl = TextEditingController();
  final _webdavPassCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final config = await context.read<AppState>().api.getConfig();
      final storage = config['storage'] as Map<String, dynamic>;
      _provider = storage['provider'] as String? ?? 'azure_blob';
      switch (_provider) {
        case 'azure_blob':
          _containerCtrl.text = storage['container'] as String? ?? '';
          _azurePrefixCtrl.text = storage['prefix'] as String? ?? 'camcontrol/';
          _accountUrlCtrl.text = storage['account_url'] as String? ?? '';
          break;
        case 'local':
          _localPathCtrl.text = storage['path'] as String? ?? './captures';
          break;
        case 's3':
          _bucketCtrl.text = storage['bucket'] as String? ?? '';
          _s3PrefixCtrl.text = storage['prefix'] as String? ?? 'camcontrol/';
          _endpointCtrl.text = storage['endpoint_url'] as String? ?? '';
          _regionCtrl.text = storage['region'] as String? ?? '';
          break;
        case 'webdav':
          _baseUrlCtrl.text = storage['base_url'] as String? ?? '';
          _remoteDirCtrl.text = storage['remote_dir'] as String? ?? 'camcontrol';
          _webdavUserCtrl.text = storage['username'] as String? ?? '';
          break;
      }
    } catch (e) {
      _error = 'Could not load current storage config: $e';
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  void dispose() {
    for (final c in [
      _containerCtrl,
      _azurePrefixCtrl,
      _connectionStringCtrl,
      _accountUrlCtrl,
      _localPathCtrl,
      _bucketCtrl,
      _s3PrefixCtrl,
      _endpointCtrl,
      _regionCtrl,
      _accessKeyCtrl,
      _secretKeyCtrl,
      _baseUrlCtrl,
      _remoteDirCtrl,
      _webdavUserCtrl,
      _webdavPassCtrl,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic> _buildConfig() {
    switch (_provider) {
      case 'azure_blob':
        return {
          'provider': 'azure_blob',
          'container': _containerCtrl.text.trim(),
          'prefix': _azurePrefixCtrl.text.trim(),
          'connection_string': _connectionStringCtrl.text,
          'account_url': _accountUrlCtrl.text.trim(),
        };
      case 's3':
        return {
          'provider': 's3',
          'bucket': _bucketCtrl.text.trim(),
          'prefix': _s3PrefixCtrl.text.trim(),
          'endpoint_url':
              _endpointCtrl.text.trim().isEmpty ? null : _endpointCtrl.text.trim(),
          'region': _regionCtrl.text.trim().isEmpty ? null : _regionCtrl.text.trim(),
          'access_key': _accessKeyCtrl.text,
          'secret_key': _secretKeyCtrl.text,
        };
      case 'webdav':
        return {
          'provider': 'webdav',
          'base_url': _baseUrlCtrl.text.trim(),
          'remote_dir': _remoteDirCtrl.text.trim(),
          'username': _webdavUserCtrl.text.trim(),
          'password': _webdavPassCtrl.text,
        };
      default:
        return {'provider': 'local', 'path': _localPathCtrl.text.trim()};
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _saving = true; _error = null; });
    try {
      await context.read<AppState>().api.setStorage(_buildConfig());
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
      appBar: AppBar(title: const Text('Storage provider')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (_error != null) ...[
              Text(_error!, style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 12),
            ],
            DropdownButtonFormField<String>(
              initialValue: _provider,
              decoration: const InputDecoration(
                labelText: 'Provider',
                border: OutlineInputBorder(),
              ),
              items: const [
                DropdownMenuItem(
                    value: 'azure_blob', child: Text('Azure Blob Storage')),
                DropdownMenuItem(value: 'local', child: Text('Local folder')),
                DropdownMenuItem(
                    value: 's3', child: Text('S3-compatible (AWS/MinIO/B2)')),
                DropdownMenuItem(value: 'webdav', child: Text('WebDAV')),
              ],
              onChanged: (v) => setState(() => _provider = v ?? _provider),
            ),
            const SizedBox(height: 16),
            if (_provider == 'azure_blob') ..._buildAzureFields(),
            if (_provider == 'local') ..._buildLocalFields(),
            if (_provider == 's3') ..._buildS3Fields(),
            if (_provider == 'webdav') ..._buildWebDavFields(),
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

  List<Widget> _buildAzureFields() {
    return [
      TextFormField(
        controller: _containerCtrl,
        decoration: const InputDecoration(
          labelText: 'Container name',
          border: OutlineInputBorder(),
        ),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _azurePrefixCtrl,
        decoration: const InputDecoration(
          labelText: 'Blob path prefix',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _connectionStringCtrl,
        obscureText: true,
        decoration: const InputDecoration(
          labelText: 'Connection string',
          hintText: 'Leave blank to use managed identity via Account URL instead',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _accountUrlCtrl,
        decoration: const InputDecoration(
          labelText: 'Account URL (for managed identity, no connection string)',
          hintText: 'https://<account>.blob.core.windows.net',
          border: OutlineInputBorder(),
        ),
      ),
    ];
  }

  List<Widget> _buildLocalFields() {
    return [
      TextFormField(
        controller: _localPathCtrl,
        decoration: const InputDecoration(
          labelText: 'Folder path on the gateway host',
          border: OutlineInputBorder(),
        ),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
    ];
  }

  List<Widget> _buildS3Fields() {
    return [
      TextFormField(
        controller: _bucketCtrl,
        decoration: const InputDecoration(
          labelText: 'Bucket name',
          border: OutlineInputBorder(),
        ),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _s3PrefixCtrl,
        decoration: const InputDecoration(
          labelText: 'Key prefix',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _endpointCtrl,
        decoration: const InputDecoration(
          labelText: 'Endpoint URL (blank for AWS S3, set for MinIO/B2)',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _regionCtrl,
        decoration: const InputDecoration(
          labelText: 'Region',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _accessKeyCtrl,
        decoration: const InputDecoration(
          labelText: 'Access key',
          hintText: 'Leave blank to keep the existing key unchanged',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _secretKeyCtrl,
        obscureText: true,
        decoration: const InputDecoration(
          labelText: 'Secret key',
          hintText: 'Leave blank to keep the existing key unchanged',
          border: OutlineInputBorder(),
        ),
      ),
    ];
  }

  List<Widget> _buildWebDavFields() {
    return [
      TextFormField(
        controller: _baseUrlCtrl,
        decoration: const InputDecoration(
          labelText: 'WebDAV base URL',
          hintText: 'https://cloud.example.com/remote.php/dav/files/user',
          border: OutlineInputBorder(),
        ),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _remoteDirCtrl,
        decoration: const InputDecoration(
          labelText: 'Remote directory',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _webdavUserCtrl,
        decoration: const InputDecoration(
          labelText: 'Username',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _webdavPassCtrl,
        obscureText: true,
        decoration: const InputDecoration(
          labelText: 'Password',
          hintText: 'Leave blank to keep the existing password unchanged',
          border: OutlineInputBorder(),
        ),
      ),
    ];
  }
}
