import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models/camera.dart';
import '../models/media_file.dart';

class ApiException implements Exception {
  ApiException(this.status, this.message);
  final int status;
  final String message;
  @override
  String toString() => 'ApiException($status): $message';
}

class ApiService {
  ApiService(this._baseUrl, this._apiKey, this._token);

  final String Function() _baseUrl;
  final String Function() _apiKey;
  final Future<String> Function() _token;

  Future<Map<String, String>> authHeaders() async {
    final token = await _token();
    final key = _apiKey();
    return {
      'Content-Type': 'application/json',
      if (token.isNotEmpty) 'Authorization': 'Bearer $token',
      if (key.isNotEmpty) 'X-API-Key': key,
    };
  }

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${_baseUrl()}$path').replace(queryParameters: query);

  void _check(http.Response res) {
    if (res.statusCode >= 400) {
      String message = res.body;
      try {
        final decoded = jsonDecode(res.body);
        if (decoded is Map && decoded['detail'] != null) {
          message = decoded['detail'].toString();
        }
      } catch (_) {}
      throw ApiException(res.statusCode, message);
    }
  }

  Future<Map<String, dynamic>> health() async {
    final res = await http.get(_uri('/api/health'));
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<List<Camera>> listCameras() async {
    final res = await http.get(_uri('/api/cameras'), headers: await authHeaders());
    _check(res);
    final list = jsonDecode(res.body) as List;
    return list
        .map((e) => Camera.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Scans the gateway host's own LAN subnet for candidate cameras.
  /// Can take several seconds since it probes the whole /24.
  Future<List<DiscoveredCamera>> discoverCameras() async {
    final res = await http
        .get(_uri('/api/discover'), headers: await authHeaders())
        .timeout(const Duration(seconds: 30));
    _check(res);
    final list = jsonDecode(res.body) as List;
    return list
        .map((e) => DiscoveredCamera.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Raw JPEG bytes for one live-view poll of [cameraId].
  /// Some backends (e.g. the SSH mmap-scrape fallback) may need several
  /// slow retries server-side, so this allows a generous ceiling.
  Future<Uint8List> fetchSnapshot(String cameraId) async {
    final res = await http
        .get(_uri('/api/cameras/$cameraId/snapshot'), headers: await authHeaders())
        .timeout(const Duration(seconds: 60));
    _check(res);
    return res.bodyBytes;
  }

  Future<Map<String, dynamic>> captureAndStore(String cameraId) async {
    final res = await http.post(
      _uri('/api/cameras/$cameraId/capture'),
      headers: await authHeaders(),
    );
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<List<MediaFile>> listMedia(String cameraId) async {
    final res = await http.get(
      _uri('/api/cameras/$cameraId/media'),
      headers: await authHeaders(),
    );
    _check(res);
    final list = jsonDecode(res.body) as List;
    return list
        .map((e) => MediaFile.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Uri mediaDownloadUri(String cameraId, String path) => _uri(
        '/api/cameras/$cameraId/media/download',
        {'path': path},
      );

  Future<Map<String, dynamic>> startRecording(String cameraId) async {
    final res = await http.post(
      _uri('/api/cameras/$cameraId/record/start'),
      headers: await authHeaders(),
    );
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> stopRecording(String cameraId) async {
    final res = await http.post(
      _uri('/api/cameras/$cameraId/record/stop'),
      headers: await authHeaders(),
    );
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> recordingStatus(String cameraId) async {
    final res = await http.get(
      _uri('/api/cameras/$cameraId/record/status'),
      headers: await authHeaders(),
    );
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLiveViewStatus(String cameraId) async {
    final res = await http.get(
      _uri('/api/cameras/$cameraId/live_view'),
      headers: await authHeaders(),
    );
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getConfig() async {
    final res = await http.get(_uri('/api/config'), headers: await authHeaders());
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<void> setCameras(List<Map<String, dynamic>> cameras) async {
    final res = await http.put(
      _uri('/api/config/cameras'),
      headers: await authHeaders(),
      body: jsonEncode(cameras),
    );
    _check(res);
  }

  Future<void> setStorage(Map<String, dynamic> storage) async {
    final res = await http.put(
      _uri('/api/config/storage'),
      headers: await authHeaders(),
      body: jsonEncode(storage),
    );
    _check(res);
  }
}

