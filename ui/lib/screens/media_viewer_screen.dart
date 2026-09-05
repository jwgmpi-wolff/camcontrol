import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
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

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final uri = state.api.mediaDownloadUri(widget.cameraId, widget.file.path);
    final headers =
        state.apiKey.isNotEmpty ? {'X-API-Key': state.apiKey} : <String, String>{};

    return Scaffold(
      appBar: AppBar(title: Text(widget.file.path)),
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
