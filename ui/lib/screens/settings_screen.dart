import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../main.dart';
import '../models/gateway_profile.dart';
import 'camera_edit_screen.dart';
import 'discovery_screen.dart';
import 'storage_settings_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  static final _readmeUri = Uri.parse(
    'https://github.com/jwgmpi-wolff/camcontrol/blob/main/README.md',
  );

  late TextEditingController _nameCtrl;
  late TextEditingController _urlCtrl;
  late TextEditingController _keyCtrl;
  late TextEditingController _userCtrl;
  final _passCtrl = TextEditingController();
  bool _obscureKey = true;
  bool _obscurePass = true;
  bool _saved = false;
  bool _loggingIn = false;
  String? _loginError;
  String _mode = 'gateway';

  @override
  void initState() {
    super.initState();
    _loadFromActiveProfile();
  }

  void _loadFromActiveProfile() {
    final profile = context.read<AppState>().activeProfile;
    _nameCtrl = TextEditingController(text: profile.name);
    _urlCtrl = TextEditingController(text: profile.baseUrl);
    _keyCtrl = TextEditingController(text: profile.apiKey);
    _userCtrl = TextEditingController(text: profile.username);
    _mode = profile.mode;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _urlCtrl.dispose();
    _keyCtrl.dispose();
    _userCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _saveProfile() async {
    final state = context.read<AppState>();
    await state.saveProfile(
      GatewayProfile(
        name: _nameCtrl.text.trim().isEmpty
            ? (_mode == 'direct' ? 'Camera' : 'Gateway')
            : _nameCtrl.text.trim(),
        baseUrl: _urlCtrl.text.trim(),
        apiKey: _keyCtrl.text.trim(),
        username: state.activeProfile.username,
        token: state.activeProfile.token,
        mode: _mode,
        directCameras: state.activeProfile.directCameras,
      ),
      index: state.activeProfileIndex,
    );
    setState(() => _saved = true);
    await Future<void>.delayed(const Duration(seconds: 2));
    if (mounted) setState(() => _saved = false);
  }

  Future<void> _addProfile(String name, String baseUrl) async {
    final state = context.read<AppState>();
    await state.saveProfile(GatewayProfile(name: name, baseUrl: baseUrl));
    await state.selectProfile(state.profiles.length - 1);
    setState(_loadFromActiveProfile);
  }

  Future<void> _addDirectProfile() async {
    final state = context.read<AppState>();
    await state.saveProfile(
      GatewayProfile(name: 'Direct cameras', baseUrl: '', mode: 'direct'),
    );
    await state.selectProfile(state.profiles.length - 1);
    setState(_loadFromActiveProfile);
  }

  Future<void> _login() async {
    setState(() {
      _loggingIn = true;
      _loginError = null;
    });
    try {
      await context
          .read<AppState>()
          .login(_userCtrl.text.trim(), _passCtrl.text);
      _passCtrl.clear();
    } catch (e) {
      _loginError = e.toString();
    } finally {
      if (mounted) setState(() => _loggingIn = false);
    }
  }

  Future<void> _openReadme() async {
    final opened = await launchUrl(
      _readmeUri,
      mode: LaunchMode.externalApplication,
    );
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the CamControl README')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Connection',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          DropdownButton<int>(
            isExpanded: true,
            value: state.activeProfileIndex,
            items: [
              for (var i = 0; i < state.profiles.length; i++)
                DropdownMenuItem(value: i, child: Text(state.profiles[i].name)),
            ],
            onChanged: (i) async {
              if (i == null) return;
              await state.selectProfile(i);
              setState(_loadFromActiveProfile);
            },
          ),
          Row(
            children: [
              TextButton.icon(
                icon: const Icon(Icons.add),
                label: const Text('Add Local'),
                onPressed: () =>
                    _addProfile('Local', 'http://192.168.1.x:8080'),
              ),
              TextButton.icon(
                icon: const Icon(Icons.cloud_outlined),
                label: const Text('Add Azure'),
                onPressed: () => _addProfile(
                  'Azure',
                  'https://<your-app>.azurewebsites.net',
                ),
              ),
              TextButton.icon(
                icon: const Icon(Icons.videocam_outlined),
                label: const Text('Add Direct camera'),
                onPressed: _addDirectProfile,
              ),
              if (state.profiles.length > 1)
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  tooltip: 'Delete this profile',
                  onPressed: () async {
                    await state.deleteProfile(state.activeProfileIndex);
                    setState(_loadFromActiveProfile);
                  },
                ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _nameCtrl,
            decoration: const InputDecoration(
              labelText: 'Profile name',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.label_outline),
            ),
          ),
          const SizedBox(height: 16),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(
                value: 'gateway',
                label: Text('Gateway'),
                icon: Icon(Icons.dns_outlined),
              ),
              ButtonSegment(
                value: 'direct',
                label: Text('Direct camera'),
                icon: Icon(Icons.videocam_outlined),
              ),
            ],
            selected: {_mode},
            onSelectionChanged: (s) => setState(() => _mode = s.first),
          ),
          const SizedBox(height: 16),
          if (_mode == 'gateway') ...[
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
                labelText: 'API Key (legacy, optional)',
                hintText: 'Only needed for admin-only endpoints',
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
          ] else ...[
            Text(
              'Cameras for this profile are added from the Camera tab '
              '(tap the + button there).',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade400),
            ),
          ],
          const SizedBox(height: 24),
          FilledButton.icon(
            icon: Icon(_saved ? Icons.check : Icons.save),
            label: Text(_saved ? 'Saved' : 'Save'),
            onPressed: _saveProfile,
          ),
          if (_mode == 'gateway') ...[
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 12),
          Text('Account', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          if (state.token.isNotEmpty)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.verified_user, color: Colors.green),
              title: Text('Signed in as ${state.username}'),
              trailing: TextButton(
                onPressed: () => state.logout(),
                child: const Text('Log out'),
              ),
            )
          else ...[
            TextField(
              controller: _userCtrl,
              decoration: const InputDecoration(
                labelText: 'Username',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.person_outline),
              ),
              autocorrect: false,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _passCtrl,
              obscureText: _obscurePass,
              decoration: InputDecoration(
                labelText: 'Password',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.lock_outline),
                suffixIcon: IconButton(
                  icon: Icon(
                      _obscurePass ? Icons.visibility : Icons.visibility_off),
                  onPressed: () => setState(() => _obscurePass = !_obscurePass),
                ),
              ),
              onSubmitted: (_) => _login(),
            ),
            if (_loginError != null) ...[
              const SizedBox(height: 8),
              Text(_loginError!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 12),
            FilledButton.icon(
              icon: _loggingIn
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.login),
              label: const Text('Log in'),
              onPressed: _loggingIn ? null : _login,
            ),
          ],
          ],
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 12),
          Text('Live view refresh', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(
            state.pollIntervalSeconds == 0
                ? 'Using each camera\'s recommended interval'
                : 'Every ${state.pollIntervalSeconds}s',
            style: const TextStyle(fontSize: 12),
          ),
          Slider(
            value: state.pollIntervalSeconds.toDouble(),
            min: 0,
            max: 30,
            divisions: 30,
            label: state.pollIntervalSeconds == 0
                ? 'Auto'
                : '${state.pollIntervalSeconds}s',
            onChanged: (v) => state.setPollIntervalSeconds(v.round()),
          ),
          if (_mode == 'gateway') ...[
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
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 12),
          Text('CamControl', style: Theme.of(context).textTheme.titleMedium),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.menu_book_outlined),
            title: const Text('README'),
            subtitle: const Text('Setup, usage, and latest release details'),
            trailing: const Icon(Icons.open_in_new),
            onTap: _openReadme,
          ),
        ],
      ),
    );
  }
}
