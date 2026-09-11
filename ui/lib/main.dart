import 'dart:async';
import 'dart:convert';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'models/camera.dart';
import 'models/direct_camera.dart';
import 'models/gateway_profile.dart';
import 'services/api_service.dart';
import 'screens/multiview_screen.dart';
import 'screens/media_browser_screen.dart';
import 'screens/settings_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(prefs)..refreshCameras(),
      child: const CamControlApp(),
    ),
  );
}

class AppState extends ChangeNotifier {
  AppState(this._prefs) {
    _loadProfiles();
    _pollIntervalSeconds = _prefs.getInt('pollIntervalSeconds') ?? 0;
  }

  final SharedPreferences _prefs;
  List<GatewayProfile> profiles = [];
  int _activeIndex = 0;
  int _pollIntervalSeconds = 0; // 0 = use each camera's own default

  GatewayProfile get activeProfile => profiles[_activeIndex];
  int get activeProfileIndex => _activeIndex;

  String get baseUrl => profiles.isEmpty ? '' : activeProfile.baseUrl;
  String get apiKey => profiles.isEmpty ? '' : activeProfile.apiKey;
  String get token => profiles.isEmpty ? '' : activeProfile.token;
  String get username => profiles.isEmpty ? '' : activeProfile.username;

  /// True when the active profile connects straight to cameras' own IPs,
  /// bypassing the camera_bridge gateway entirely.
  bool get isDirectMode => profiles.isNotEmpty && activeProfile.isDirect;
  List<DirectCamera> get directCameras =>
      profiles.isEmpty ? [] : activeProfile.directCameras;

  Future<void> addDirectCamera(String name, String host) async {
    if (profiles.isEmpty) return;
    activeProfile.directCameras.add(
      DirectCamera(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        name: name,
        host: host,
      ),
    );
    await _saveProfiles();
    notifyListeners();
  }

  Future<void> updateDirectCamera(
    String id, {
    required String name,
    required String host,
  }) async {
    if (profiles.isEmpty) return;
    final idx = activeProfile.directCameras.indexWhere((c) => c.id == id);
    if (idx == -1) return;
    activeProfile.directCameras[idx] = DirectCamera(id: id, name: name, host: host);
    await _saveProfiles();
    notifyListeners();
  }

  Future<void> removeDirectCamera(String id) async {
    if (profiles.isEmpty) return;
    activeProfile.directCameras.removeWhere((c) => c.id == id);
    await _saveProfiles();
    notifyListeners();
  }

  /// 0 means "use each camera's own recommended interval".
  int get pollIntervalSeconds => _pollIntervalSeconds;

  late final ApiService api = ApiService(() => baseUrl, () => apiKey, () => token);

  String status = 'disconnected';
  List<Camera> cameras = [];

  void _loadProfiles() {
    final raw = _prefs.getString('gatewayProfiles');
    if (raw != null) {
      final list = jsonDecode(raw) as List;
      profiles = list
          .map((e) => GatewayProfile.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    if (profiles.isEmpty) {
      // Migrate the old single baseUrl/apiKey prefs into a "Local" profile.
      final legacyUrl = _prefs.getString('baseUrl') ?? 'http://192.168.1.x:21416';
      final legacyKey = _prefs.getString('apiKey') ?? '';
      profiles = [GatewayProfile(name: 'Local', baseUrl: legacyUrl, apiKey: legacyKey)];
    }
    _activeIndex = _prefs.getInt('activeProfileIndex') ?? 0;
    if (_activeIndex < 0 || _activeIndex >= profiles.length) _activeIndex = 0;
  }

  Future<void> _saveProfiles() async {
    await _prefs.setString(
      'gatewayProfiles',
      jsonEncode(profiles.map((p) => p.toJson()).toList()),
    );
    await _prefs.setInt('activeProfileIndex', _activeIndex);
  }

  Future<void> selectProfile(int index) async {
    if (index < 0 || index >= profiles.length) return;
    _activeIndex = index;
    await _prefs.setInt('activeProfileIndex', _activeIndex);
    notifyListeners();
    await refreshCameras();
  }

  /// Adds a new profile (if [index] is null / out of range) or updates the
  /// profile at [index] in place.
  Future<void> saveProfile(GatewayProfile profile, {int? index}) async {
    if (index != null && index >= 0 && index < profiles.length) {
      profiles[index] = profile;
    } else {
      profiles.add(profile);
      index = profiles.length - 1;
    }
    await _saveProfiles();
    notifyListeners();
    if (index == _activeIndex) await refreshCameras();
  }

  Future<void> deleteProfile(int index) async {
    if (index < 0 || index >= profiles.length) return;
    profiles.removeAt(index);
    if (profiles.isEmpty) {
      profiles = [GatewayProfile(name: 'Local', baseUrl: 'http://192.168.1.x:21416')];
    }
    if (_activeIndex >= profiles.length) _activeIndex = 0;
    await _saveProfiles();
    notifyListeners();
    await refreshCameras();
  }

  Future<void> login(String username, String password) async {
    final issuedToken = await api.login(username, password);
    activeProfile.username = username;
    activeProfile.token = issuedToken;
    await _saveProfiles();
    notifyListeners();
  }

  void logout() {
    activeProfile.token = '';
    _saveProfiles();
    notifyListeners();
  }

  Future<void> setPollIntervalSeconds(int seconds) async {
    _pollIntervalSeconds = seconds;
    await _prefs.setInt('pollIntervalSeconds', seconds);
    notifyListeners();
  }

  // Stored on-device only (SharedPreferences) so a reconnect QR/manual entry
  // is available if the home Wi-Fi network ever changes -- never sent to the
  // gateway or over the network.
  String get wifiSsid => _prefs.getString('wifiSsid') ?? '';
  String get wifiPassword => _prefs.getString('wifiPassword') ?? '';
  String get wifiSecurity => _prefs.getString('wifiSecurity') ?? 'WPA';

  Future<void> setWifiCredentials({
    required String ssid,
    required String password,
    required String security,
  }) async {
    await _prefs.setString('wifiSsid', ssid);
    await _prefs.setString('wifiPassword', password);
    await _prefs.setString('wifiSecurity', security);
    notifyListeners();
  }

  Future<void> refreshCameras() async {
    if (isDirectMode) {
      // No gateway to poll -- the direct camera view fetches its own frames.
      status = 'ok';
      cameras = [];
      notifyListeners();
      return;
    }
    try {
      await api.health();
      cameras = await api.listCameras();
      status = 'ok';
    } catch (_) {
      status = 'unreachable';
      cameras = [];
    }
    notifyListeners();
  }
}


class CamControlApp extends StatelessWidget {
  const CamControlApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wolff IoT Platform for Cameras',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0078D4), // Azure blue
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const MainShell(),
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;
  StreamSubscription<Uri>? _linkSub;

  @override
  void initState() {
    super.initState();
    _initDeepLinks();
  }

  Future<void> _initDeepLinks() async {
    final appLinks = AppLinks();
    try {
      final initial = await appLinks.getInitialLink();
      if (initial != null) _handleDeepLink(initial);
    } catch (_) {
      // No initial link (cold start without a deep link) -- nothing to do.
    }
    _linkSub = appLinks.uriLinkStream.listen(_handleDeepLink);
  }

  /// `camcontrol://configure?url=<gateway-url>&key=<api-key>&name=<profile-name>`
  /// Provisions (or updates) a Gateway profile without the user typing it in.
  void _handleDeepLink(Uri uri) {
    if (!mounted) return;
    if (uri.scheme != 'camcontrol' || uri.host != 'configure') return;
    final url = uri.queryParameters['url'];
    if (url == null || url.isEmpty) return;
    final apiKey = uri.queryParameters['key'] ?? '';
    final name = uri.queryParameters['name'] ?? 'Azure';
    final state = context.read<AppState>();
    final existingIndex =
        state.profiles.indexWhere((p) => p.baseUrl == url && !p.isDirect);
    state
        .saveProfile(
          GatewayProfile(name: name, baseUrl: url, apiKey: apiKey),
          index: existingIndex == -1 ? null : existingIndex,
        )
        .then((_) => state.selectProfile(
              existingIndex == -1 ? state.profiles.length - 1 : existingIndex,
            ));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Configured gateway "$name" ($url)')),
    );
  }

  @override
  void dispose() {
    _linkSub?.cancel();
    super.dispose();
  }

  static const _cameraScreens = [
    MultiViewScreen(),
    MediaBrowserScreen(),
    SettingsScreen(),
  ];
  static const _cameraLabels = ['Cameras', 'Media', 'Settings'];
  static const _cameraIcons = [Icons.grid_view, Icons.video_library, Icons.settings];

  // Direct mode has no gateway, so there's no media library to browse.
  static const _directScreens = [MultiViewScreen(), SettingsScreen()];
  static const _directLabels = ['Camera', 'Settings'];
  static const _directIcons = [Icons.videocam, Icons.settings];

  @override
  Widget build(BuildContext context) {
    final isDirect = context.watch<AppState>().isDirectMode;
    final screens = isDirect ? _directScreens : _cameraScreens;
    final labels = isDirect ? _directLabels : _cameraLabels;
    final icons = isDirect ? _directIcons : _cameraIcons;
    final index = _index < screens.length ? _index : 0;

    return Scaffold(
      body: screens[index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          for (var i = 0; i < labels.length; i++)
            NavigationDestination(icon: Icon(icons[i]), label: labels[i]),
        ],
      ),
    );
  }
}
