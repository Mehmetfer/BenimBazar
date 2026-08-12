import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/listing_media.dart';
import 'edit_listing_screen.dart';
import 'listing_detail_screen.dart';

/// Owner's listings including pending moderation — photos visible via all_photo_urls.
class MyListingsScreen extends StatefulWidget {
  const MyListingsScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<MyListingsScreen> createState() => _MyListingsScreenState();
}

class _MyListingsScreenState extends State<MyListingsScreen> {
  List<dynamic> _items = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await api.myListings();
      if (!mounted) return;
      setState(() {
        _items = list;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bg,
        title: Text(
          'İlanlarım',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : _items.isEmpty
                  ? Center(
                      child: Text(
                        'Henüz ilan yok.\nFotoğraflı ilan oluşturun.',
                        textAlign: TextAlign.center,
                        style: GoogleFonts.montserrat(color: AppColors.muted),
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: _items.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 14),
                        itemBuilder: (_, i) {
                          final item = Map<String, dynamic>.from(_items[i] as Map);
                          final status = item['status']?.toString() ?? '';
                          final photos = resolvePhotoUrls(item);
                          return InkWell(
                            onTap: () async {
                              await Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => ListingDetailScreen(
                                    listing: item,
                                    user: widget.user,
                                  ),
                                ),
                              );
                              _load();
                            },
                            child: Container(
                              decoration: BoxDecoration(
                                color: AppColors.bgCard,
                                border: Border.all(color: AppColors.line),
                              ),
                              clipBehavior: Clip.antiAlias,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  ListingHeroMedia(
                                    listing: item,
                                    height: 180,
                                    borderRadius: 0,
                                  ),
                                  Padding(
                                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          item['title']?.toString() ?? '',
                                          style: GoogleFonts.montserrat(
                                            fontWeight: FontWeight.w700,
                                            fontSize: 16,
                                          ),
                                        ),
                                        const SizedBox(height: 6),
                                        Text(
                                          '$status · ${photos.length} fotoğraf',
                                          style: GoogleFonts.montserrat(
                                            color: AppColors.muted,
                                            fontSize: 12,
                                          ),
                                        ),
                                        const SizedBox(height: 10),
                                        Row(
                                          children: [
                                            OutlinedButton.icon(
                                              onPressed: () async {
                                                final ok = await Navigator.of(context).push<bool>(
                                                  MaterialPageRoute(
                                                    builder: (_) => EditListingScreen(
                                                      user: widget.user,
                                                      listing: item,
                                                    ),
                                                  ),
                                                );
                                                if (ok == true) _load();
                                              },
                                              icon: const Icon(Icons.edit_outlined, size: 18),
                                              label: const Text('Düzenle / Fotoğraf'),
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
