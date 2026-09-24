import 'dart:typed_data';

enum FeedHealth { connecting, live, stalled, offline }

class FeedHealthMonitor {
  FeedHealthMonitor({
    DateTime? startedAt,
    this.stallAfter = const Duration(seconds: 15),
    this.offlineAfter = const Duration(seconds: 12),
    this.failuresBeforeOffline = 2,
  }) : _startedAt = startedAt ?? DateTime.now();

  factory FeedHealthMonitor.forPollInterval(
    Duration pollInterval, {
    DateTime? startedAt,
  }) {
    final stallSeconds = (pollInterval.inMilliseconds * 4 / 1000).ceil().clamp(
      15,
      300,
    );
    final offlineSeconds = (pollInterval.inMilliseconds * 2 / 1000)
        .ceil()
        .clamp(12, 300);
    return FeedHealthMonitor(
      startedAt: startedAt,
      stallAfter: Duration(seconds: stallSeconds),
      offlineAfter: Duration(seconds: offlineSeconds),
    );
  }

  final Duration stallAfter;
  final Duration offlineAfter;
  final int failuresBeforeOffline;

  DateTime _startedAt;
  DateTime? _lastSuccessAt;
  DateTime? _lastChangeAt;
  Uint8List? _lastFrame;
  bool _hasObservedChange = false;
  int _consecutiveFailures = 0;

  void recordFrame(Uint8List frame, {DateTime? now}) {
    final timestamp = now ?? DateTime.now();
    if (!_framesEqual(_lastFrame, frame)) {
      _hasObservedChange = _lastFrame != null;
      _lastFrame = frame;
      _lastChangeAt = timestamp;
    }
    _lastSuccessAt = timestamp;
    _consecutiveFailures = 0;
  }

  void recordFailure() {
    _consecutiveFailures++;
  }

  void resume({DateTime? now}) {
    _startedAt = now ?? DateTime.now();
    _lastSuccessAt = null;
    _lastChangeAt = null;
    _lastFrame = null;
    _hasObservedChange = false;
    _consecutiveFailures = 0;
  }

  FeedHealth status({DateTime? now}) {
    final timestamp = now ?? DateTime.now();
    if (_consecutiveFailures >= failuresBeforeOffline) {
      return FeedHealth.offline;
    }
    final lastSuccess = _lastSuccessAt;
    if (lastSuccess == null) {
      return timestamp.difference(_startedAt) >= offlineAfter
          ? FeedHealth.offline
          : FeedHealth.connecting;
    }
    if (timestamp.difference(lastSuccess) >= offlineAfter) {
      return FeedHealth.offline;
    }
    final lastChange = _lastChangeAt;
    if (lastChange != null && timestamp.difference(lastChange) >= stallAfter) {
      return FeedHealth.stalled;
    }
    return _hasObservedChange ? FeedHealth.live : FeedHealth.connecting;
  }

  static bool _framesEqual(Uint8List? previous, Uint8List current) {
    if (previous == null || previous.length != current.length) return false;
    for (var i = 0; i < current.length; i++) {
      if (previous[i] != current[i]) return false;
    }
    return true;
  }
}
