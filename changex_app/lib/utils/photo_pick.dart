import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';

/// Picked image bytes ready for upload (web + mobile).
class PickedPhoto {
  PickedPhoto({
    required this.bytes,
    required this.filename,
    required this.contentType,
  });

  final Uint8List bytes;
  final String filename;
  final String contentType;
}

String _contentTypeFor(String name) {
  final n = name.toLowerCase();
  if (n.endsWith('.png')) return 'image/png';
  if (n.endsWith('.webp')) return 'image/webp';
  if (n.endsWith('.gif')) return 'image/gif';
  return 'image/jpeg';
}

/// Robust gallery pick: ImagePicker (web-safe) → FilePicker fallback.
Future<List<PickedPhoto>> pickListingPhotos({
  int maxCount = 9,
  ImagePicker? picker,
}) async {
  final out = <PickedPhoto>[];
  final imagePicker = picker ?? ImagePicker();

  // 1) image_picker_for_web — most reliable on Flutter web / mobile browsers
  try {
    final files = await imagePicker.pickMultiImage(
      imageQuality: 85,
      maxWidth: 2000,
    );
    for (final f in files) {
      if (out.length >= maxCount) break;
      final bytes = await f.readAsBytes();
      if (bytes.isEmpty) continue;
      final name = f.name.isEmpty ? 'photo.jpg' : f.name;
      out.add(
        PickedPhoto(
          bytes: bytes,
          filename: name,
          contentType: _contentTypeFor(name),
        ),
      );
    }
    if (out.isNotEmpty) return out;
  } catch (_) {
    // fall through
  }

  // 2) file_picker with withData (required on web)
  try {
    final result = await FilePicker.pickFiles(
      type: FileType.image,
      allowMultiple: true,
      withData: true,
    );
    if (result != null) {
      for (final f in result.files) {
        if (out.length >= maxCount) break;
        final bytes = f.bytes;
        if (bytes == null || bytes.isEmpty) continue;
        final name = f.name.isEmpty ? 'photo.jpg' : f.name;
        out.add(
          PickedPhoto(
            bytes: Uint8List.fromList(bytes),
            filename: name,
            contentType: _contentTypeFor(name),
          ),
        );
      }
    }
  } catch (_) {
    // fall through
  }

  return out;
}

Future<PickedPhoto?> pickListingCamera({ImagePicker? picker}) async {
  final imagePicker = picker ?? ImagePicker();
  try {
    final shot = await imagePicker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
      maxWidth: 2000,
    );
    if (shot == null) return null;
    final bytes = await shot.readAsBytes();
    if (bytes.isEmpty) return null;
    final name = shot.name.isEmpty ? 'camera.jpg' : shot.name;
    return PickedPhoto(
      bytes: bytes,
      filename: name,
      contentType: 'image/jpeg',
    );
  } catch (_) {
    return null;
  }
}
