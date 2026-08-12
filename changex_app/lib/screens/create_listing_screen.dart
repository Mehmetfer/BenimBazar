import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';

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
  final _itemName = TextEditingController(text: 'Ürün');
  final _madalyon = TextEditingController(text: '1');
  final _dirhem = TextEditingController(text: '0');
  final _mandal = TextEditingController(text: '0');
  final _picker = ImagePicker();
  String _category = 'Elektronik';
  final String _condition = 'good';
  bool _busy = false;
  String? _error;
  final List<_PickedPhoto> _photos = [];

  @override
  void dispose() {
    _title.dispose();
    _desc.dispose();
    _wanted.dispose();
    _location.dispose();
    _itemName.dispose();
    _madalyon.dispose();
    _dirhem.dispose();
    _mandal.dispose();
    super.dispose();
  }

  Future<void> _pickPhotos() async {
    try {
      final files = await _picker.pickMultiImage(
        imageQuality: 85,
        maxWidth: 2000,
      );
      if (files.isEmpty) return;
      for (final f in files) {
        if (_photos.length >= 9) break;
        final bytes = await f.readAsBytes();
        if (bytes.isEmpty) continue;
        final name = f.name.toLowerCase();
        var ctype = 'image/jpeg';
        if (name.endsWith('.png')) ctype = 'image/png';
        if (name.endsWith('.webp')) ctype = 'image/webp';
        if (name.endsWith('.gif')) ctype = 'image/gif';
        setState(() {
          _photos.add(
            _PickedPhoto(
              bytes: bytes,
              filename: f.name.isEmpty ? 'photo.jpg' : f.name,
              contentType: ctype,
            ),
          );
        });
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Görsel seçilemedi')),
      );
    }
  }

  Future<void> _submit() async {
    if (_title.text.trim().length < 2) {
      setState(() => _error = 'Başlık en az 2 karakter olmalı');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final urls = <String>[];
      for (final photo in _photos) {
        final url = await api.uploadImage(
          bytes: photo.bytes,
          filename: photo.filename,
          contentType: photo.contentType,
        );
        urls.add(url);
      }
      final created = await api.createListing({
        'title': _title.text.trim(),
        'description': _desc.text.trim(),
        'category': _category,
        'subcategory': '',
        'condition': _condition,
        'location': _location.text.trim(),
        'wanted_items': _wanted.text.trim(),
        'accept_categories': [_category],
        'photo_urls': urls,
        'items': [
          {
            'name': _itemName.text.trim().isEmpty ? 'Ürün' : _itemName.text.trim(),
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
          'İçeriğiniz incelemeye gönderildi.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg)),
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'Kayıt oluşturulamadı');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Takas kaydı',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const PlatformBanner(),
          const SizedBox(height: 16),
          Text(
            'Ürün görselleri',
            style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: 110,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (var i = 0; i < _photos.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 10),
                    child: Stack(
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.memory(
                            _photos[i].bytes is Uint8List
                                ? _photos[i].bytes as Uint8List
                                : Uint8List.fromList(_photos[i].bytes),
                            width: 110,
                            height: 110,
                            fit: BoxFit.cover,
                          ),
                        ),
                        Positioned(
                          top: 4,
                          right: 4,
                          child: InkWell(
                            onTap: () => setState(() => _photos.removeAt(i)),
                            child: Container(
                              padding: const EdgeInsets.all(4),
                              color: Colors.black54,
                              child: const Icon(Icons.close, size: 16, color: Colors.white),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                if (_photos.length < 9)
                  InkWell(
                    onTap: _busy ? null : _pickPhotos,
                    child: Container(
                      width: 110,
                      height: 110,
                      decoration: BoxDecoration(
                        color: AppColors.bgElevated,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.gold.withValues(alpha: 0.5)),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.add_a_photo_outlined, color: AppColors.gold),
                          const SizedBox(height: 6),
                          Text(
                            'Resim ekle',
                            style: GoogleFonts.montserrat(
                              color: AppColors.gold,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'En fazla 9 görsel · JPG/PNG/WEBP',
            style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 11),
          ),
          const SizedBox(height: 16),
          TextField(controller: _title, decoration: const InputDecoration(labelText: 'Başlık')),
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
              'Spor',
              'Ev',
              'Kitap',
              'Moda',
              'Otomobil',
              'Telefon',
              'Diğer',
            ].map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
            onChanged: (v) => setState(() => _category = v ?? _category),
            decoration: const InputDecoration(labelText: 'Kategori'),
          ),
          const SizedBox(height: 10),
          TextField(controller: _location, decoration: const InputDecoration(labelText: 'Konum')),
          const SizedBox(height: 10),
          TextField(
            controller: _wanted,
            decoration: const InputDecoration(labelText: 'İstenen ürünler'),
          ),
          const SizedBox(height: 10),
          TextField(controller: _itemName, decoration: const InputDecoration(labelText: 'Ürün adı')),
          const SizedBox(height: 10),
          Text('Takas değeri (sunucu hesaplar)', style: GoogleFonts.montserrat(color: AppColors.muted)),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: TextField(controller: _madalyon, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Madalyon'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _dirhem, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Dirhem'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _mandal, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Mandal'))),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: AppColors.danger)),
          ],
          const SizedBox(height: 20),
          SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_busy ? 'Kaydediliyor…' : 'Takas kaydı oluştur'),
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

  final List<int> bytes;
  final String filename;
  final String contentType;
}
