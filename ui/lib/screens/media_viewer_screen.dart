import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:video_player/video_player.dart';

import '../main.dart';
import '../models/media_file.dart';

class MediaViewerScreen extends StatefulWidget {
  const MediaViewerScreen({
    super.key,
    required this.cameraId,
    required this.file,
  });

  final String cameraId;
  final MediaFile file;

  @override
  State<MediaViewerScreen> createState() => _MediaViewerScreenState();
}

class _MediaViewerScreenState extends State<MediaViewerScreen> {
  VideoPlayerController? _controller;
  bool _sharing = false;

  @override
  void initState() {
    super.initState();
    if (widget.file.mediaType == 'video') {
      final state = context.read<AppState>();
      final uri = state.api.mediaDownloadUri(widget.cameraId, widget.file.path);
      final headers = state.apiKey.isNotEmpty
          ? {'X-API-Key': state.apiKey}
          : <String, String>{};
      _controller = VideoPlayerController.networkUrl(uri, httpHeaders: headers)
        ..initialize().then((_) {
          if (mounted) setState(() {});
          _controller!.play();
        });
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _share() async {
    if (_sharing) return;
    setState(() => _sharing = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final state = context.read<AppState>();
      final uri = state.api.mediaDownloadUri(widget.cameraId, widget.file.path);
      final headers = <String, String>{
        if (state.token.isNotEmpty) 'Authorization': 'Bearer ${state.token}',
        if (state.apiKey.isNotEmpty) 'X-API-Key': state.apiKey,
      };
      final res = await http.get(uri, headers: headers);
      if (res.statusCode >= 400) {
        throw Exception('Download failed: HTTP ${res.statusCode}');
      }
      final dir = await getTemporaryDirectory();
      final fileName = widget.file.path.split('/').last;
      final tempFile = File('${dir.path}/$fileName');
      await tempFile.writeAsBytes(res.bodyBytes);
      await Share.shareXFiles([XFile(tempFile.path)], text: widget.file.path);
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Share failed: $e')));
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final uri = state.api.mediaDownloadUri(widget.cameraId, widget.file.path);
    final headers =
        state.apiKey.isNotEmpty ? {'X-API-Key': state.apiKey} : <String, String>{};

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.file.path),
        actions: [
          IconButton(
            icon: _sharing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.share),
            tooltip: 'Share',
            onPressed: _sharing ? null : _share,
          ),
        ],
      ),
      body: Center(
        child: widget.file.mediaType == 'video'
            ? _buildVideo()
            : Image.network(uri.toString(), headers: headers, fit: BoxFit.contain),
      ),
      floatingActionButton: _controller != null && _controller!.value.isInitialized
          ? FloatingActionButton(
              onPressed: () => setState(() {
                _controller!.value.isPlaying
                    ? _controller!.pause()
                    : _controller!.play();
              }),
              child: Icon(
                _controller!.value.isPlaying ? Icons.pause : Icons.play_arrow,
              ),
            )
          : null,
    );
  }

  Widget _buildVideo() {
    if (_controller == null || !_controller!.value.isInitialized) {
      return const CircularProgressIndicator();
    }
    return AspectRatio(
      aspectRatio: _controller!.value.aspectRatio,
      child: VideoPlayer(_controller!),
    );
  }
}
