import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import 'camera_tile.dart';

/// Grid of live-updating tiles, one per configured camera.
class MultiViewScreen extends StatelessWidget {
  const MultiViewScreen({super.key});

  int _columnsFor(double width) {
    if (width >= 1200) return 4;
    if (width >= 800) return 3;
    if (width >= 500) return 2;
    return 1;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Wolff IoT Platform for Cameras'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => state.refreshCameras(),
          ),
        ],
      ),
      body: state.status == 'unreachable'
          ? _GatewayUnreachable(baseUrl: state.baseUrl)
          : state.cameras.isEmpty
              ? const _NoCameras()
              : LayoutBuilder(
                  builder: (context, constraints) {
                    final columns = _columnsFor(constraints.maxWidth);
                    return GridView.builder(
                      padding: const EdgeInsets.all(12),
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: columns,
                        mainAxisSpacing: 12,
                        crossAxisSpacing: 12,
                        childAspectRatio: 4 / 3,
                      ),
                      itemCount: state.cameras.length,
                      itemBuilder: (context, i) =>
                          CameraTile(camera: state.cameras[i]),
                    );
                  },
                ),
    );
  }
}

class _GatewayUnreachable extends StatelessWidget {
  const _GatewayUnreachable({required this.baseUrl});
  final String baseUrl;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off, size: 64),
          const SizedBox(height: 16),
          const Text('Gateway unreachable'),
          const SizedBox(height: 4),
          Text(baseUrl, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _NoCameras extends StatelessWidget {
  const _NoCameras();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.videocam_off, size: 64),
          SizedBox(height: 16),
          Text('No cameras configured yet'),
          SizedBox(height: 4),
          Text('Add one from Settings → Cameras'),
        ],
      ),
    );
  }
}
