/// Safe origin for resolving relative `/uploads/...` paths.
///
/// `Uri.base.origin` throws when the app runs under a non-http scheme
/// (e.g. Flutter widget tests use `file://`). In that case return empty
/// so callers can keep relative paths without crashing the widget tree.
String safeOrigin() {
  try {
    final base = Uri.base;
    if (base.scheme == 'http' || base.scheme == 'https') {
      return base.origin;
    }
  } catch (_) {
    // fall through
  }
  return '';
}

String resolveMediaUrl(String raw) {
  final s = raw.trim();
  if (s.isEmpty) return s;
  if (s.startsWith('http://') || s.startsWith('https://')) return s;
  if (s.startsWith('/')) {
    final origin = safeOrigin();
    return origin.isEmpty ? s : '$origin$s';
  }
  return s;
}
