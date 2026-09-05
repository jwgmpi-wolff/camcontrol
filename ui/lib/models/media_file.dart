class MediaFile {
  MediaFile({
    required this.path,
    required this.size,
    required this.modifiedEpoch,
    required this.mediaType,
  });

  final String path;
  final int size;
  final int modifiedEpoch;
  final String mediaType; // "image" | "video" | "other"

  DateTime get modified =>
      DateTime.fromMillisecondsSinceEpoch(modifiedEpoch * 1000);

  factory MediaFile.fromJson(Map<String, dynamic> json) => MediaFile(
        path: json['path'] as String,
        size: json['size'] as int,
        modifiedEpoch: json['modified_epoch'] as int,
        mediaType: json['media_type'] as String,
      );

  String get sizeLabel {
    if (size < 1024) return '$size B';
    if (size < 1024 * 1024) return '${(size / 1024).toStringAsFixed(1)} KB';
    return '${(size / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
