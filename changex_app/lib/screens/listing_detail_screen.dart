import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';
import 'login_screen.dart';

class ListingDetailScreen extends StatefulWidget {
  const ListingDetailScreen({
    super.key,
    required this.listing,
    required this.user,
  });

  final Map<String, dynamic> listing;
  final Map<String, dynamic>? user;

  @override
  State<ListingDetailScreen> createState() => _ListingDetailScreenState();
}

class _ListingDetailScreenState extends State<ListingDetailScreen> {
  final _offerName = TextEditingController(text: 'Teklif ürünüm');
  final _madalyon = TextEditingController(text: '1');
  final _dirhem = TextEditingController(text: '0');
  final _mandal = TextEditingController(text: '0');
  bool _busy = false;
  String? _result;

  @override
  void dispose() {
    _offerName.dispose();
    _madalyon.dispose();
    _dirhem.dispose();
    _mandal.dispose();
    super.dispose();
  }

  Future<void> _offer() async {
    if (widget.user == null) {
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
      );
      return;
    }
    setState(() {
      _busy = true;
      _result = null;
    });
    try {
      final res = await api.createOffer({
        'listing_id': widget.listing['id'],
        'offer_items': [
          {
            'name': _offerName.text.trim(),
            'value': {
              'madalyon': int.tryParse(_madalyon.text) ?? 0,
              'dirhem': int.tryParse(_dirhem.text) ?? 0,
              'mandal': int.tryParse(_mandal.text) ?? 0,
            },
          }
        ],
      });
      final match = res['match'] as Map<String, dynamic>?;
      setState(() {
        if (match != null && match['exact_match'] == true) {
          _result = 'Tam eşleşme! Durum: ${res['state']}';
        } else if (match != null) {
          final gap = match['gap'] as Map<String, dynamic>;
          _result =
              'Fark: ${gap['madalyon']} Madalyon · ${gap['dirhem']} Dirhem · ${gap['mandal']} Mandal\n'
              'Fark gerçek para ile kapatılamaz. Ürün ekleyin veya yeni teklif verin.';
        } else {
          _result = 'Teklif gönderildi · ${res['state']}';
        }
      });
    } on ApiException catch (e) {
      setState(() => _result = e.message);
    } catch (_) {
      setState(() => _result = 'Teklif gönderilemedi');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final value = Map<String, dynamic>.from(widget.listing['value'] as Map? ?? {});
    final owner = Map<String, dynamic>.from(widget.listing['owner'] as Map? ?? {});
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
          Text(
            widget.listing['title']?.toString() ?? '',
            style: GoogleFonts.montserrat(fontSize: 26, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          Text(
            '${widget.listing['category']} · ${owner['username']} · skor ${owner['change_score']}',
            style: GoogleFonts.montserrat(color: AppColors.muted),
          ),
          const SizedBox(height: 12),
          ValueChip(value: value),
          const SizedBox(height: 14),
          Text(
            widget.listing['description']?.toString() ?? '',
            style: GoogleFonts.montserrat(height: 1.4),
          ),
          if ((widget.listing['wanted_items']?.toString() ?? '').isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              'İstiyor: ${widget.listing['wanted_items']}',
              style: GoogleFonts.montserrat(color: AppColors.gold),
            ),
          ],
          const SizedBox(height: 24),
          Text(
            'Takas teklifi ver',
            style: GoogleFonts.montserrat(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const PlatformBanner(),
          const SizedBox(height: 12),
          TextField(
            controller: _offerName,
            decoration: const InputDecoration(labelText: 'Teklif ürün adı'),
          ),
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
          const SizedBox(height: 16),
          SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: _busy ? null : _offer,
              child: Text(
                widget.user == null ? 'Giriş yap & teklif ver' : 'Takas teklifi ver',
              ),
            ),
          ),
          if (_result != null) ...[
            const SizedBox(height: 14),
            Text(_result!, style: GoogleFonts.montserrat(height: 1.35)),
          ],
        ],
      ),
    );
  }
}
