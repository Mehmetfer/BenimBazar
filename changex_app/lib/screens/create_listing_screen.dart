import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';

/// Instagram / Letgo tarzı takas ilanı oluşturma — fotoğraf önce.
class CreateListingScreen extends StatefulWidget {
  const CreateListingScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<CreateListingScreen> createState() => _CreateListingScreenState();
}

class _CreateListingScreenState extends State<CreateListingScreen> {
  final _title = TextEditingController();
  final _desc = TextEditingController();
  final _wanted = TextEditingController();
  final _location = TextEditingController();
  final _brand = TextEditingController();
  final _model = TextEditingController();
  final _itemName = TextEditingController(text: 'Ürün');
  final _madalyon = TextEditingController(text: '1');
  final _dirhem = TextEditingController(text: '0');
  final _mandal = TextEditingController(text: '0');
  final _page = PageController();
  final _cameraPicker = ImagePicker();

  String _category = 'Elektronik';
  String _condition = 'good';
  bool _busy = false;
  String? _error;
  String? _status;
  int _photoIndex = 0;
  final List<_PickedPhoto> _photos = [];

  @override
  void dispose() {
    _title.dispose();
    _desc.dispose();
    _wanted.dispose();
    _location.dispose();
    _brand.dispose();
    _model.dispose();
    _itemName.dispose();
    _madalyon.dispose();
    _dirhem.dispose();
    _mandal.dispose();
    _page.dispose();
    super.dispose();
  }

  Future<void> _pickFromGallery() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.image,
        allowMultiple: true,
        withData: true, // web için zorunlu
      );
      if (result == null || result.files.isEmpty) return;
      var added = 0;
      for (final f in result.files) {
        if (_photos.length >= 9) break;
        final bytes = f.bytes;
        if (bytes == null || bytes.isEmpty) continue;
        final name = (f.name).toLowerCase();
        var ctype = 'image/jpeg';
        if (name.endsWith('.png')) ctype = 'image/png';
        if (name.endsWith('.webp')) ctype = 'image/webp';
        if (name.endsWith('.gif')) ctype = 'image/gif';
        _photos.add(
          _PickedPhoto(
            bytes: Uint8List.fromList(bytes),
            filename: f.name.isEmpty ? 'photo.jpg' : f.name,
            contentType: ctype,
          ),
        );
        added++;
      }
      if (!mounted) return;
      setState(() {});
      if (added == 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Görsel okunamadı — tekrar deneyin')),
        );
      } else if (_photos.isNotEmpty) {
        _page.jumpToPage(_photos.length - 1);
        setState(() => _photoIndex = _photos.length - 1);
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Galeri açılamadı: $e')),
      );
    }
  }

  Future<void> _pickFromCamera() async {
    try {
      final shot = await _cameraPicker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
        maxWidth: 2000,
      );
      if (shot == null) return;
      if (_photos.length >= 9) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('En fazla 9 fotoğraf')),
        );
        return;
      }
      final bytes = await shot.readAsBytes();
      if (bytes.isEmpty) return;
      setState(() {
        _photos.add(
          _PickedPhoto(
            bytes: bytes,
            filename: shot.name.isEmpty ? 'camera.jpg' : shot.name,
            contentType: 'image/jpeg',
          ),
        );
      });
    } catch (e) {
      // Web'de kamera yoksa galeriye düş
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Kamera kullanılamadı — galeriden seçin')),
      );
      await _pickFromGallery();
    }
  }

  Future<void> _submit() async {
    if (_photos.isEmpty) {
      setState(() => _error = 'En az 1 ürün fotoğrafı ekleyin');
      return;
    }
    if (_title.text.trim().length < 2) {
      setState(() => _error = 'Başlık en az 2 karakter olmalı');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _status = 'Fotoğraflar yükleniyor…';
    });
    try {
      final urls = <String>[];
      for (var i = 0; i < _photos.length; i++) {
        setState(() => _status = 'Fotoğraf ${i + 1}/${_photos.length} yükleniyor…');
        final photo = _photos[i];
        final url = await api.uploadImage(
          bytes: photo.bytes,
          filename: photo.filename,
          contentType: photo.contentType,
        );
        urls.add(url);
      }
      setState(() => _status = 'İlan kaydediliyor…');
      final brand = _brand.text.trim();
      final model = _model.text.trim();
      final created = await api.createListing({
        'title': _title.text.trim(),
        'description': _desc.text.trim(),
        'category': _category,
        'subcategory': '',
        'condition': _condition,
        'location': _location.text.trim(),
        'location_city': _location.text.trim(),
        'brand': brand,
        'model_name': model,
        'wanted_items': _wanted.text.trim(),
        'wanted_categories': [_category],
        'accept_categories': [_category],
        'photo_urls': urls,
        'attributes': {
          if (brand.isNotEmpty) 'MARKA': brand,
          if (model.isNotEmpty) 'MODEL': model,
        },
        'items': [
          {
            'name': _itemName.text.trim().isEmpty
                ? (_title.text.trim().isEmpty ? 'Ürün' : _title.text.trim())
                : _itemName.text.trim(),
            'value': {
              'madalyon': int.tryParse(_madalyon.text) ?? 0,
              'dirhem': int.tryParse(_dirhem.text) ?? 0,
              'mandal': int.tryParse(_mandal.text) ?? 0,
            },
          }
        ],
      });
      if (!mounted) return;
      final msg = created['user_message']?.toString() ??
          'İlanınız onay kutusuna gönderildi.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _status = null;
      });
    } catch (e) {
      setState(() {
        _error = 'Kayıt oluşturulamadı';
        _status = null;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final heroH = MediaQuery.sizeOf(context).width.clamp(280.0, 520.0);
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bg,
        title: Text(
          'Yeni takas ilanı',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        ),
      ),
      body: ListView(
        children: [
          // —— Instagram/Letgo tarzı fotoğraf düzlemi ——
          SizedBox(
            height: heroH,
            width: double.infinity,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (_photos.isEmpty)
                  ColoredBox(
                    color: AppColors.bgCard,
                    child: InkWell(
                      onTap: _busy ? null : _pickFromGallery,
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.add_a_photo_outlined,
                            size: 56,
                            color: AppColors.gold.withValues(alpha: 0.9),
                          ),
                          const SizedBox(height: 14),
                          Text(
                            'ÜRÜN FOTOĞRAFI EKLE',
                            style: GoogleFonts.montserrat(
                              color: AppColors.gold,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 1.1,
                              fontSize: 14,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Galeriden seçin · en fazla 9 fotoğraf',
                            style: GoogleFonts.montserrat(
                              color: AppColors.muted,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                  )
                else
                  PageView.builder(
                    controller: _page,
                    itemCount: _photos.length,
                    onPageChanged: (i) => setState(() => _photoIndex = i),
                    itemBuilder: (_, i) => Image.memory(
                      _photos[i].bytes,
                      fit: BoxFit.cover,
                      width: double.infinity,
                      height: heroH,
                    ),
                  ),
                if (_photos.isNotEmpty)
                  Positioned(
                    top: 12,
                    right: 12,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        '${_photoIndex + 1}/${_photos.length}',
                        style: GoogleFonts.montserrat(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ),
                if (_photos.isNotEmpty)
                  Positioned(
                    top: 12,
                    left: 12,
                    child: IconButton.filled(
                      style: IconButton.styleFrom(backgroundColor: Colors.black54),
                      onPressed: _busy
                          ? null
                          : () => setState(() {
                                _photos.removeAt(_photoIndex);
                                if (_photoIndex >= _photos.length && _photoIndex > 0) {
                                  _photoIndex--;
                                }
                              }),
                      icon: const Icon(Icons.delete_outline, color: Colors.white),
                    ),
                  ),
              ],
            ),
          ),
          // Aksiyon şeridi
          Container(
            color: Colors.black,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.gold,
                      side: const BorderSide(color: AppColors.gold),
                    ),
                    onPressed: _busy ? null : _pickFromGallery,
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('Galeriden'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.ink,
                      side: const BorderSide(color: AppColors.line),
                    ),
                    onPressed: _busy ? null : _pickFromCamera,
                    icon: const Icon(Icons.photo_camera_outlined),
                    label: const Text('Kamera'),
                  ),
                ),
              ],
            ),
          ),
          if (_photos.isNotEmpty)
            SizedBox(
              height: 72,
              child: ListView.separated(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
                scrollDirection: Axis.horizontal,
                itemCount: _photos.length + (_photos.length < 9 ? 1 : 0),
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (_, i) {
                  if (i == _photos.length) {
                    return InkWell(
                      onTap: _busy ? null : _pickFromGallery,
                      child: Container(
                        width: 64,
                        decoration: BoxDecoration(
                          border: Border.all(color: AppColors.gold),
                          color: AppColors.bgElevated,
                        ),
                        child: const Icon(Icons.add, color: AppColors.gold),
                      ),
                    );
                  }
                  return InkWell(
                    onTap: () {
                      _page.jumpToPage(i);
                      setState(() => _photoIndex = i);
                    },
                    child: Container(
                      width: 64,
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: i == _photoIndex ? AppColors.gold : AppColors.line,
                          width: i == _photoIndex ? 2 : 1,
                        ),
                      ),
                      child: Image.memory(_photos[i].bytes, fit: BoxFit.cover),
                    ),
                  );
                },
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const PlatformBanner(),
                const SizedBox(height: 16),
                TextField(
                  controller: _title,
                  decoration: const InputDecoration(
                    labelText: 'Başlık / MARKA MODEL',
                    hintText: 'Örn: MERCEDES BENZ A180 AMG',
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _brand,
                        decoration: const InputDecoration(labelText: 'Marka'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: _model,
                        decoration: const InputDecoration(labelText: 'Model'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _desc,
                  maxLines: 3,
                  decoration: const InputDecoration(labelText: 'Açıklama'),
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  value: _category,
                  items: const [
                    'Elektronik',
                    'Telefon',
                    'Otomobil',
                    'Spor',
                    'Ev',
                    'Kitap',
                    'Moda',
                    'Bilgisayar',
                    'Diğer',
                  ].map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
                  onChanged: (v) => setState(() => _category = v ?? _category),
                  decoration: const InputDecoration(labelText: 'Kategori'),
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  value: _condition,
                  items: const [
                    ('new', 'Sıfır'),
                    ('like_new', 'Sıfır ayarında'),
                    ('good', 'İyi'),
                    ('fair', 'Orta'),
                    ('poor', 'Kötü'),
                  ]
                      .map(
                        (e) => DropdownMenuItem(value: e.$1, child: Text(e.$2)),
                      )
                      .toList(),
                  onChanged: (v) => setState(() => _condition = v ?? _condition),
                  decoration: const InputDecoration(labelText: 'Durum'),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _location,
                  decoration: const InputDecoration(labelText: 'Konum'),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _wanted,
                  decoration: const InputDecoration(
                    labelText: 'Ne ile takas etmek istiyorsun?',
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  'Takas değeri (para yok — Mandal sistemi)',
                  style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _madalyon,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Madalyon'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: _dirhem,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Dirhem'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: _mandal,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Mandal'),
                      ),
                    ),
                  ],
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
                  height: 54,
                  child: FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: Text(
                      _busy
                          ? 'Gönderiliyor…'
                          : 'Fotoğraflı ilanı onaya gönder',
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PickedPhoto {
  _PickedPhoto({
    required this.bytes,
    required this.filename,
    required this.contentType,
  });

  final Uint8List bytes;
  final String filename;
  final String contentType;
}
