import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

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
  String _category = 'Elektronik';
  final String _condition = 'good';
  bool _busy = false;
  String? _error;

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

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await api.createListing({
        'title': _title.text.trim(),
        'description': _desc.text.trim(),
        'category': _category,
        'subcategory': '',
        'condition': _condition,
        'location': _location.text.trim(),
        'wanted_items': _wanted.text.trim(),
        'accept_categories': [_category],
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
