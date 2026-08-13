import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../utils/listing_status_ux.dart';
import '../widgets/listing_media.dart';
import 'create_listing_screen.dart';
import 'edit_listing_screen.dart';
import 'listing_detail_screen.dart';

/// Owner's listings including pending moderation — photos via all_photo_urls.
class MyListingsScreen extends StatefulWidget {
  const MyListingsScreen({
    super.key,
    required this.user,
    this.initialItems,
  });

  final Map<String, dynamic> user;

  /// Widget-test injection (skips network).
  final List<Map<String, dynamic>>? initialItems;

  @override
  State<MyListingsScreen> createState() => _MyListingsScreenState();
}

class _MyListingsScreenState extends State<MyListingsScreen> {
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  String? _error;
  MyListingsFilter _filter = MyListingsFilter.all;

  @override
  void initState() {
    super.initState();
    if (widget.initialItems != null) {
      _items = List<Map<String, dynamic>>.from(widget.initialItems!);
      _loading = false;
    } else {
      _load();
    }
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
        _items = list
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList(growable: false);
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'İlanlarınız yüklenemedi. Yenileyin.';
        _loading = false;
      });
    }
  }

  List<Map<String, dynamic>> get _visible =>
      _items.where((e) => listingMatchesFilter(e, _filter)).toList();

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
          IconButton(
            onPressed: widget.initialItems != null ? null : _load,
            icon: const Icon(Icons.refresh),
            tooltip: 'Yenile',
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(
              'Onay bekleyen ilanlar ana sayfada görünmez — burada güvenle durur.',
              style: GoogleFonts.montserrat(
                color: AppColors.muted,
                fontSize: 12,
                height: 1.35,
              ),
            ),
          ),
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final f in MyListingsFilter.values)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ChoiceChip(
                      label: Text(myListingsFilterLabel(f)),
                      selected: _filter == f,
                      onSelected: (_) => setState(() => _filter = f),
                      selectedColor: AppColors.gold,
                      labelStyle: GoogleFonts.montserrat(
                        color: _filter == f ? AppColors.bg : AppColors.ink,
                        fontWeight: FontWeight.w600,
                        fontSize: 12,
                      ),
                      backgroundColor: AppColors.bgElevated,
                      side: BorderSide(
                        color: _filter == f ? AppColors.gold : AppColors.line,
                      ),
                      showCheckmark: false,
                    ),
                  ),
              ],
            ),
          ),
          Expanded(child: _buildBody()),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => CreateListingScreen(user: widget.user),
            ),
          );
          if (widget.initialItems == null) _load();
        },
        backgroundColor: AppColors.gold,
        foregroundColor: AppColors.bg,
        icon: const Icon(Icons.add_a_photo_outlined),
        label: Text(
          'Yeni ilan',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _error!,
                textAlign: TextAlign.center,
                style: GoogleFonts.montserrat(color: AppColors.danger),
              ),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Tekrar dene')),
            ],
          ),
        ),
      );
    }
    if (_items.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'Henüz ilan yok.\nFotoğraflı ilan oluşturun — inceleme süresince İlanlarım’da görünür.',
            textAlign: TextAlign.center,
            style: GoogleFonts.montserrat(color: AppColors.muted, height: 1.4),
          ),
        ),
      );
    }
    final visible = _visible;
    if (visible.isEmpty) {
      return Center(
        child: Text(
          'Bu filtrede ilan yok.',
          style: GoogleFonts.montserrat(color: AppColors.muted),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: widget.initialItems != null ? () async {} : _load,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 100),
        itemCount: visible.length,
        separatorBuilder: (_, __) => const SizedBox(height: 14),
        itemBuilder: (_, i) => _MyListingCard(
          item: visible[i],
          user: widget.user,
          onChanged: () {
            if (widget.initialItems == null) _load();
          },
        ),
      ),
    );
  }
}

class _MyListingCard extends StatelessWidget {
  const _MyListingCard({
    required this.item,
    required this.user,
    required this.onChanged,
  });

  final Map<String, dynamic> item;
  final Map<String, dynamic> user;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final state = resolveListingUxState(item);
    final chipColor = listingUxChipColor(state);
    final reason = item['moderation_reason']?.toString().trim() ?? '';

    return InkWell(
      onTap: () async {
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ListingDetailScreen(listing: item, user: user),
          ),
        );
        onChanged();
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
                  Row(
                    children: [
                      Flexible(
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: chipColor.withValues(alpha: 0.18),
                              border: Border.all(
                                color: chipColor.withValues(alpha: 0.5),
                              ),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              listingUxChipLabel(state),
                              style: GoogleFonts.montserrat(
                                color: chipColor,
                                fontWeight: FontWeight.w800,
                                fontSize: 11,
                                letterSpacing: 0.3,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          listingImageStatusLine(item),
                          textAlign: TextAlign.right,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.montserrat(
                            color: AppColors.muted,
                            fontSize: 11,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    item['title']?.toString() ?? '',
                    style: GoogleFonts.montserrat(
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    listingUxBody(item),
                    style: GoogleFonts.montserrat(
                      color: AppColors.muted,
                      fontSize: 12,
                      height: 1.35,
                    ),
                  ),
                  if (reason.isNotEmpty &&
                      (state == ListingUxState.rejected ||
                          state == ListingUxState.editRequired)) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Gerekçe: $reason',
                      style: GoogleFonts.montserrat(
                        color: AppColors.danger,
                        fontSize: 12,
                        height: 1.3,
                      ),
                    ),
                  ],
                  if (listingUxEditable(state)) ...[
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      onPressed: () async {
                        final ok = await Navigator.of(context).push<bool>(
                          MaterialPageRoute(
                            builder: (_) => EditListingScreen(
                              user: user,
                              listing: item,
                            ),
                          ),
                        );
                        if (ok == true) onChanged();
                      },
                      icon: const Icon(Icons.edit_outlined, size: 18),
                      label: const Text('Düzenle / Fotoğraf'),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
