import 'package:flutter/material.dart';

import '../utils/feed_health_monitor.dart';

class FeedHealthIndicator extends StatelessWidget {
  const FeedHealthIndicator({super.key, required this.health});

  final FeedHealth health;

  @override
  Widget build(BuildContext context) {
    final (label, color, icon) = switch (health) {
      FeedHealth.connecting => ('Connecting', Colors.grey, Icons.circle),
      FeedHealth.live => ('Live', Colors.green, Icons.circle),
      FeedHealth.stalled => ('Stalled', Colors.orange, Icons.warning_rounded),
      FeedHealth.offline => ('Offline', Colors.red, Icons.error),
    };
    return Tooltip(
      message: label,
      child: Semantics(
        label: 'Feed status: $label',
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 11, color: color),
            const SizedBox(width: 3),
            Text(
              label,
              style: Theme.of(context).textTheme.labelSmall
                  ?.copyWith(color: color, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}

class FeedUnavailable extends StatelessWidget {
  const FeedUnavailable({super.key, required this.health, this.detail});

  final FeedHealth health;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    if (health == FeedHealth.connecting) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            SizedBox(height: 8),
            Text('Verifying live feed'),
          ],
        ),
      );
    }
    final stalled = health == FeedHealth.stalled;
    final message = stalled ? 'Feed is not updating' : 'Camera is offline';
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              stalled ? Icons.warning_rounded : Icons.videocam_off,
              size: 36,
              color: stalled ? Colors.orange : Colors.red,
            ),
            const SizedBox(height: 8),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            if (detail != null) ...[
              const SizedBox(height: 4),
              Text(
                detail!,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
