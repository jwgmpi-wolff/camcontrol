import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.status, this.message);
  final int status;
  final String message;
  @override
  String toString() => 'ApiException($status): $message';
}

class ApiService {
  ApiService(this._baseUrl, this._apiKey);

  final String Function() _baseUrl;
  final String Function() _apiKey;

  Map<String, String> get _headers {
    final key = _apiKey();
    return {
      'Content-Type': 'application/json',
      if (key.isNotEmpty) 'X-API-Key': key,
    };
  }

  Uri _uri(String path) => Uri.parse('${_baseUrl()}$path');

  Future<Map<String, dynamic>> _getJson(String path) async {
    final res = await http.get(_uri(path), headers: _headers);
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _postJson(String path) async {
    final res = await http.post(_uri(path), headers: _headers);
    _check(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  void _check(http.Response res) {
    if (res.statusCode >= 400) {
      throw ApiException(res.statusCode, res.body);
    }
  }

  Future<Map<String, dynamic>> health() => _getJson('/api/health');
  Future<Map<String, dynamic>> deviceInfo() => _getJson('/api/device');
  Future<Map<String, dynamic>> startStream() => _postJson('/api/stream/start');
  Future<Map<String, dynamic>> stopStream() => _postJson('/api/stream/stop');
  Future<Map<String, dynamic>> snapshot() => _postJson('/api/snapshot');
  Future<Map<String, dynamic>> startRecording() =>
      _postJson('/api/recording/start');
  Future<Map<String, dynamic>> stopRecording() =>
      _postJson('/api/recording/stop');
  Future<Map<String, dynamic>> recordings() => _getJson('/api/recordings');

  /// Returns raw JPEG bytes for the live view polling loop.
  Future<Uint8List> fetchFrame() async {
    final key = _apiKey();
    final headers = <String, String>{
      if (key.isNotEmpty) 'X-API-Key': key,
    };
    final res = await http
        .get(_uri('/api/stream/frame'), headers: headers)
        .timeout(const Duration(seconds: 3));
    if (res.statusCode != 200) throw ApiException(res.statusCode, 'frame error');
    return res.bodyBytes;
  }
}
