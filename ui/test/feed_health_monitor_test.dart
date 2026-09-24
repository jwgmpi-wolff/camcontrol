import 'dart:typed_data';

import 'package:camcontrol/utils/feed_health_monitor.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final start = DateTime(2026, 9, 24, 12);

  test('reports offline when no initial frame arrives', () {
    final monitor = FeedHealthMonitor(
      startedAt: start,
      offlineAfter: const Duration(seconds: 10),
    );

    expect(
      monitor.status(now: start.add(const Duration(seconds: 9))),
      FeedHealth.connecting,
    );
    expect(
      monitor.status(now: start.add(const Duration(seconds: 10))),
      FeedHealth.offline,
    );
  });

  test('reports stalled when successful frames stop changing', () {
    final monitor = FeedHealthMonitor(
      startedAt: start,
      stallAfter: const Duration(seconds: 15),
    );
    final frame = Uint8List.fromList([1, 2, 3]);

    monitor.recordFrame(frame, now: start);
    monitor.recordFrame(frame, now: start.add(const Duration(seconds: 14)));
    expect(
      monitor.status(now: start.add(const Duration(seconds: 14))),
      FeedHealth.connecting,
    );
    monitor.recordFrame(frame, now: start.add(const Duration(seconds: 15)));
    expect(
      monitor.status(now: start.add(const Duration(seconds: 15))),
      FeedHealth.stalled,
    );
  });

  test('returns to live when a stalled frame changes', () {
    final monitor = FeedHealthMonitor(startedAt: start);
    final unchangedFrame = Uint8List.fromList([1]);
    monitor.recordFrame(unchangedFrame, now: start);
    monitor.recordFrame(
      unchangedFrame,
      now: start.add(const Duration(seconds: 15)),
    );
    expect(
      monitor.status(now: start.add(const Duration(seconds: 15))),
      FeedHealth.stalled,
    );

    monitor.recordFrame(
      Uint8List.fromList([2]),
      now: start.add(const Duration(seconds: 16)),
    );

    expect(
      monitor.status(now: start.add(const Duration(seconds: 16))),
      FeedHealth.live,
    );
  });

  test('scales timeouts for a slower polling interval', () {
    final monitor = FeedHealthMonitor.forPollInterval(
      const Duration(seconds: 30),
      startedAt: start,
    );

    expect(
      monitor.status(now: start.add(const Duration(seconds: 59))),
      FeedHealth.connecting,
    );
    expect(
      monitor.status(now: start.add(const Duration(seconds: 60))),
      FeedHealth.offline,
    );
  });

  test('requires consecutive failures before reporting offline', () {
    final monitor = FeedHealthMonitor(startedAt: start);
    monitor.recordFrame(Uint8List.fromList([1]), now: start);
    monitor.recordFrame(
      Uint8List.fromList([2]),
      now: start.add(const Duration(seconds: 1)),
    );

    monitor.recordFailure();
    expect(
      monitor.status(now: start.add(const Duration(seconds: 2))),
      FeedHealth.live,
    );
    monitor.recordFailure();
    expect(
      monitor.status(now: start.add(const Duration(seconds: 3))),
      FeedHealth.offline,
    );
  });

  test('does not report live until two different frames arrive', () {
    final monitor = FeedHealthMonitor(startedAt: start);

    monitor.recordFrame(Uint8List.fromList([1]), now: start);
    expect(monitor.status(now: start), FeedHealth.connecting);

    monitor.recordFrame(
      Uint8List.fromList([2]),
      now: start.add(const Duration(seconds: 1)),
    );
    expect(
      monitor.status(now: start.add(const Duration(seconds: 1))),
      FeedHealth.live,
    );
  });
}
