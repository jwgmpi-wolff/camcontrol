import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../models/camera.dart';
import '../models/media_file.dart';
import 'media_viewer_screen.dart';

/// Lists images/videos stored on a camera's local media (e.g. SD card),
/// for cameras whose capture backend supports browsing.
class MediaBrowserScreen extends StatefulWidget {
  const MediaBrowserScreen({super.key});

  @override
  State<MediaBrowserScreen> createState() => _MediaBrowserScreenState();
}

class _MediaBrowserScreenState extends State<MediaBrowserScreen> {
  Camera? _selected;
  Future<List<MediaFile>>? _future;

  void _selectCamera(Camera camera) {
    setState(() {
      _selected = camera;
      _future = context.read<AppState>().api.listMedia(camera.id);
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (_selected == null && state.cameras.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_selected == null) _selectCamera(state.cameras.first);
      });
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Media'),
        actions: [
          if (_selected != null)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: () => _selectCamera(_selected!),
            ),
        ],
      ),
      body: Column(
        children: [
          if (state.cameras.length > 1) _buildCameraPicker(state),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildCameraPicker(AppState state) {
    return Padding(
      padding: const EdgeInsets.all(8.0),
      child: DropdownButton<Camera>(
        isExpanded: true,
        value: _selected,
        items: [
          for (final camera in state.cameras)
            DropdownMenuItem(value: camera, child: Text(camera.name)),
        ],
        onChanged: (camera) {
          if (camera != null) _selectCamera(camera);
        },
      ),
    );
  }

  Widget _buildBody() {
    if (_selected == null) {
      return const Center(child: Text('No cameras configured yet'));
    }
    return FutureBuilder<List<MediaFile>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Text(
                'This camera does not support media browsing, or it is '
                'unreachable:\n${snapshot.error}',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        final files = snapshot.data ?? [];
        if (files.isEmpty) {
          return const Center(child: Text('No captures or recordings yet'));
        }
        files.sort((a, b) => b.modifiedEpoch.compareTo(a.modifiedEpoch));
        return ListView.builder(
          itemCount: files.length,
          itemBuilder: (context, i) {
            final file = files[i];
            return ListTile(
              leading: Icon(
                file.mediaType == 'video'
                    ? Icons.movie
                    : file.mediaType == 'image'
                        ? Icons.image
                        : Icons.insert_drive_file,
              ),
              title: Text(file.path),
              subtitle: Text(
                '${file.sizeLabel} • '
                '${DateFormat.yMd().add_jm().format(file.modified)}',
              ),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => MediaViewerScreen(
                    cameraId: _selected!.id,
                    file: file,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }
}
