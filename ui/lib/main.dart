import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'services/api_service.dart';
import 'screens/home_screen.dart';
import 'screens/stream_screen.dart';
import 'screens/settings_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(prefs),
      child: const CamControlApp(),
    ),
  );
}

class AppState extends ChangeNotifier {
  AppState(this._prefs) {
    _baseUrl = _prefs.getString('baseUrl') ?? 'http://192.168.1.x:8080';
    _apiKey = _prefs.getString('apiKey') ?? '';
  }

  final SharedPreferences _prefs;
  String _baseUrl;
  String _apiKey;

  String get baseUrl => _baseUrl;
  String get apiKey => _apiKey;

  late final ApiService api = ApiService(() => _baseUrl, () => _apiKey);

  bool streaming = false;
  bool recording = false;
  Map<String, dynamic> device = {};
  String status = 'disconnected';
  Uint8List? lastFrame;

  Future<void> saveSettings(String url, String key) async {
    _baseUrl = url;
    _apiKey = key;
    await _prefs.setString('baseUrl', url);
    await _prefs.setString('apiKey', key);
    notifyListeners();
  }

  Future<void> refresh() async {
    try {
      final h = await api.health();
      streaming = h['streaming'] as bool? ?? false;
      recording = h['recording'] as bool? ?? false;
      status = h['status'] as String? ?? 'ok';
      notifyListeners();
    } catch (_) {
      status = 'unreachable';
      notifyListeners();
    }
  }

  Future<void> fetchDevice() async {
    device = await api.deviceInfo();
    notifyListeners();
  }
}

class CamControlApp extends StatelessWidget {
  const CamControlApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CamControl',
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

  static const _screens = [HomeScreen(), StreamScreen(), SettingsScreen()];
  static const _labels = ['Dashboard', 'Live View', 'Settings'];
  static const _icons = [Icons.dashboard, Icons.videocam, Icons.settings];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          for (var i = 0; i < _labels.length; i++)
            NavigationDestination(icon: Icon(_icons[i]), label: _labels[i]),
        ],
      ),
    );
  }
}
