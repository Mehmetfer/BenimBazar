import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../utils/photo_pick.dart';
import '../widgets/listing_media.dart';

/// Edit listing + add/remove photos (PATCH photo_urls).
class EditListingScreen extends StatefulWidget {
  const EditListingScreen({
    super.key,
    required this.user,
    required this.listing,
  });

  final Map<String, dynamic> user;
  final Map<String, dynamic> listing;

  @override
  State<EditListingScreen> createState() => _EditListingScreenState();
}

class _EditListingScreenState extends State<EditListingScreen> {
  late final TextEditingController _title;
  late final TextEditingController _desc;
  late final TextEditingController _wanted;
  late final TextEditingController _location;
  final List<String> _photoUrls = [];
  final List<PickedPhoto> _pending = [];
  bool _busy = false;
  String? _error;
  String? _status;

  @override
  void initState() {
    super.initState();
    _title = TextEditingController(text: widget.listing['title']?.toString() ?? '');
    _desc = TextEditingController(text: widget.listing['description']?.toString() ?? '');
    _wanted = TextEditingController(text: widget.listing['wanted_items']?.toString() ?? '');
    _location = TextEditingController(text: widget.listing['location']?.toString() ?? '');
    _photoUrls.addAll(resolvePhotoUrls(widget.listing).map(_toRelative));
  }

  String _toRelative(String s) {
    if (s.contains('/uploads/')) {
      return '/uploads/${s.split('/uploads/').last}';
    }
    return s;
  }

  @override
  void dispose() {
    _title.dispose();
    _desc.dispose();
    _wanted.dispose();
    _location.dispose();
    super.dispose();
  }

  Future<void> _addPhotos() async {
    final room = 9 - _photoUrls.length - _pending.length;
    if (room <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('En fazla 9 fotoğraf')),
      );
      return;
    }
    final picked = await pickListingPhotos(maxCount: room);
    if (!mounted) return;
    if (picked.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Görsel seçilmedi')),
      );
      return;
    }
    setState(() => _pending.addAll(picked));
  }

  Future<void> _save() async {
    if (_photoUrls.isEmpty && _pending.isEmpty) {
      setState(() => _error = 'En az 1 fotoğraf kalmalı');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _status = 'Kaydediliyor…';
    });
    try {
      final urls = List<String>.from(_photoUrls);
      for (var i = 0; i < _pending.length; i++) {
        setState(() => _status = 'Yeni fotoğraf ${i + 1}/${_pending.length}…');
        final p = _pending[i];
        final url = await api.uploadImage(
          bytes: p.bytes,
          filename: p.filename,
          contentType: p.contentType,
        );
        urls.add(url);
      }
      final id = widget.listing['id'] as int;
      final updated = await api.updateListing(id, {
        'title': _title.text.trim(),
        'description': _desc.text.trim(),
        'wanted_items': _wanted.text.trim(),
        'location': _location.text.trim(),
        'photo_urls': urls,
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            updated['user_message']?.toString() ?? 'İlan güncellendi',
          ),
        ),
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _status = null;
      });
    } catch (_) {
      setState(() {
        _error = 'Güncellenemedi';
        _status = null;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final origin = Uri.base.origin;
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bg,
        title: Text(
          'İlanı düzenle',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          Text(
            'Fotoğraflar',
            style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: 96,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (var i = 0; i < _photoUrls.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Stack(
                      children: [
                        Image.network(
                          _photoUrls[i].startsWith('/')
                              ? '$origin${_photoUrls[i]}'
                              : _photoUrls[i],
                          width: 96,
                          height: 96,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            width: 96,
                            height: 96,
                            color: AppColors.bgCard,
                            child: const Icon(Icons.broken_image),
                          ),
                        ),
                        Positioned(
                          top: 0,
                          right: 0,
                          child: IconButton(
                            style: IconButton.styleFrom(
                              backgroundColor: Colors.black54,
                              padding: EdgeInsets.zero,
                              minimumSize: const Size(28, 28),
                            ),
                            onPressed: _busy
                                ? null
                                : () => setState(() => _photoUrls.removeAt(i)),
                            icon: const Icon(Icons.close, size: 16, color: Colors.white),
                          ),
                        ),
                      ],
                    ),
                  ),
                for (final p in _pending)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Image.memory(p.bytes, width: 96, height: 96, fit: BoxFit.cover),
                  ),
                InkWell(
                  onTap: _busy ? null : _addPhotos,
                  child: Container(
                    width: 96,
                    height: 96,
                    decoration: BoxDecoration(
                      border: Border.all(color: AppColors.gold),
                      color: AppColors.bgElevated,
                    ),
                    child: const Icon(Icons.add_a_photo_outlined, color: AppColors.gold),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          TextField(
            controller: _title,
            decoration: const InputDecoration(labelText: 'Başlık'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _desc,
            maxLines: 3,
            decoration: const InputDecoration(labelText: 'Açıklama'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _location,
            decoration: const InputDecoration(labelText: 'Konum'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _wanted,
            decoration: const InputDecoration(labelText: 'Ne ile takas?'),
          ),
          if (_status != null) ...[
            const SizedBox(height: 12),
            Text(_status!, style: GoogleFonts.montserrat(color: AppColors.blue)),
          ],
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: AppColors.danger)),
          ],
          const SizedBox(height: 20),
          SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: _busy ? null : _save,
              child: Text(_busy ? 'Kaydediliyor…' : 'Kaydet'),
            ),
          ),
        ],
      ),
    );
  }
}
