import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';

/// Listing trade-status ribbon (Letgo/Instagram-style overlay).
///
/// CHANGE X copy (no money / no "sold"):
/// - TRADED → "Takas edilmiştir"
/// - closed / unavailable → "Takasa kapalı"
enum ListingTradeRibbon {
  none,
  exchanged, // Takas edilmiştir
  closed, // Takasa kapalı
}

ListingTradeRibbon resolveListingRibbon(Map<String, dynamic> listing) {
  final status = (listing['status']?.toString() ?? '').toUpperCase();
  final inv = (listing['inventory_status']?.toString() ?? '').toUpperCase();
  final mod = (listing['moderation_status']?.toString() ?? '').toUpperCase();

  if (status == 'TRADED' || inv == 'TRADED') {
    return ListingTradeRibbon.exchanged;
  }

  if (status == 'RESERVED' ||
      inv == 'RESERVED' ||
      status == 'CANCELLED' ||
      inv == 'CANCELLED' ||
      status == 'EXPIRED' ||
      inv == 'EXPIRED' ||
      status == 'SUSPENDED' ||
      mod == 'SUSPENDED' ||
      status == 'REJECTED' ||
      mod == 'REJECTED') {
    return ListingTradeRibbon.closed;
  }

  return ListingTradeRibbon.none;
}

String ribbonLabel(ListingTradeRibbon ribbon) {
  switch (ribbon) {
    case ListingTradeRibbon.exchanged:
      return 'TAKAS EDİLMİŞTİR';
    case ListingTradeRibbon.closed:
      return 'TAKASA KAPALI';
    case ListingTradeRibbon.none:
      return '';
  }
}

/// Full-bleed listing media with optional status ribbon across the image.
class ListingHeroMedia extends StatelessWidget {
  const ListingHeroMedia({
    super.key,
    required this.listing,
    this.height = 220,
    this.borderRadius = 0,
    this.showGalleryHint = true,
  });

  final Map<String, dynamic> listing;
  final double height;
  final double borderRadius;
  final bool showGalleryHint;

  @override
  Widget build(BuildContext context) {
    final photos = _photoUrls(listing);
    final ribbon = resolveListingRibbon(listing);
    final hasPhoto = photos.isNotEmpty;

    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (hasPhoto)
              Image.network(
                photos.first,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => _placeholder(),
              )
            else
              _placeholder(),
            // Soft bottom scrim for readability
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, Color(0x66000000)],
                ),
              ),
            ),
            if (showGalleryHint && photos.length > 1)
              Positioned(
                top: 12,
                right: 12,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '1/${photos.length}',
                    style: GoogleFonts.montserrat(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
            if (ribbon != ListingTradeRibbon.none)
              Center(child: TradeStatusRibbon(ribbon: ribbon)),
          ],
        ),
      ),
    );
  }

  Widget _placeholder() {
    final category = listing['category']?.toString() ?? 'Takas';
    return ColoredBox(
      color: AppColors.bgCard,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.swap_horiz, color: AppColors.gold.withValues(alpha: 0.7), size: 42),
            const SizedBox(height: 8),
            Text(
              category.toUpperCase(),
              style: GoogleFonts.montserrat(
                color: AppColors.muted,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class TradeStatusRibbon extends StatelessWidget {
  const TradeStatusRibbon({super.key, required this.ribbon});

  final ListingTradeRibbon ribbon;

  @override
  Widget build(BuildContext context) {
    final label = ribbonLabel(ribbon);
    if (label.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.88),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white24),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            ribbon == ListingTradeRibbon.exchanged
                ? Icons.check_circle_outline
                : Icons.block,
            color: Colors.white,
            size: 18,
          ),
          const SizedBox(width: 10),
          Flexible(
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: GoogleFonts.montserrat(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                fontSize: 13,
                letterSpacing: 1.1,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Icon(
            ribbon == ListingTradeRibbon.exchanged
                ? Icons.check_circle_outline
                : Icons.block,
            color: Colors.white,
            size: 18,
          ),
        ],
      ),
    );
  }
}

/// Spec strip under hero — Letgo-style quick facts (no emoji clutter).
class ListingSpecStrip extends StatelessWidget {
  const ListingSpecStrip({super.key, required this.listing});

  final Map<String, dynamic> listing;

  @override
  Widget build(BuildContext context) {
    final value = Map<String, dynamic>.from(listing['value'] as Map? ?? {});
    final location = (listing['location_city']?.toString().isNotEmpty == true)
        ? listing['location_city'].toString()
        : (listing['location']?.toString() ?? '');
    final brand = listing['brand']?.toString() ?? '';
    final preference = (listing['trade_preference']?.toString() ?? 'DIRECT_ONLY')
        .toUpperCase();
    final chainOpt = listing['chain_opt_in'] == true;
    final takasLabel = chainOpt && preference == 'CHAIN_ALLOWED'
        ? 'ZİNCİR AÇIK'
        : preference == 'DIRECT_ONLY'
            ? 'DOĞRUDAN'
            : 'TAKAS';

    final cells = <(IconData, String)>[
      (Icons.category_outlined, listing['category']?.toString() ?? '—'),
      if (brand.isNotEmpty) (Icons.sell_outlined, brand),
      (
        Icons.monetization_on_outlined,
        '${value['madalyon'] ?? 0}M ${value['dirhem'] ?? 0}D',
      ),
      if (location.isNotEmpty) (Icons.place_outlined, location),
      (Icons.swap_horiz, takasLabel),
      (Icons.tag, 'İlan: ${listing['id'] ?? '—'}'),
    ];

    return Container(
      width: double.infinity,
      color: Colors.black,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
      child: Row(
        children: [
          for (final (icon, text) in cells.take(4))
            Expanded(
              child: Column(
                children: [
                  Icon(icon, size: 16, color: AppColors.gold),
                  const SizedBox(height: 4),
                  Text(
                    text,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: GoogleFonts.montserrat(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
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

/// Structured attribute rows (MARKA, KONUM, TAKAS…) without emoji bullets.
class ListingAttributeList extends StatelessWidget {
  const ListingAttributeList({super.key, required this.listing});

  final Map<String, dynamic> listing;

  @override
  Widget build(BuildContext context) {
    final attrs = Map<String, dynamic>.from(listing['attributes'] as Map? ?? {});
    final wanted = (listing['wanted_categories'] as List?)?.cast<dynamic>() ?? [];
    final preference = (listing['trade_preference']?.toString() ?? 'DIRECT_ONLY')
        .toUpperCase();
    final chainOpt = listing['chain_opt_in'] == true;
    final ribbon = resolveListingRibbon(listing);

    String takasValue;
    if (ribbon == ListingTradeRibbon.exchanged) {
      takasValue = 'TAKAS EDİLMİŞTİR';
    } else if (ribbon == ListingTradeRibbon.closed) {
      takasValue = 'TAKASA KAPALI';
    } else if (chainOpt && preference == 'CHAIN_ALLOWED') {
      takasValue = 'EVET · ZİNCİR AÇIK';
    } else {
      takasValue = 'EVET · DOĞRUDAN';
    }

    final rows = <(String, String)>[
      if ((listing['brand']?.toString() ?? '').isNotEmpty)
        ('MARKA / MODEL', '${listing['brand']} ${listing['model_name'] ?? ''}'.trim()),
      ('KATEGORİ', listing['category']?.toString() ?? '—'),
      if ((listing['condition']?.toString() ?? '').isNotEmpty)
        ('DURUM', listing['condition'].toString()),
      if ((listing['location']?.toString() ?? '').isNotEmpty ||
          (listing['location_city']?.toString() ?? '').isNotEmpty)
        (
          'KONUM',
          (listing['location_city']?.toString().isNotEmpty == true)
              ? listing['location_city'].toString()
              : listing['location'].toString(),
        ),
      ('TAKAS', takasValue),
      if (wanted.isNotEmpty) ('İSTİYOR', wanted.map((e) => e.toString()).join(', ')),
      for (final e in attrs.entries)
        if (e.value != null && e.value.toString().trim().isNotEmpty)
          (e.key.toString().toUpperCase(), e.value.toString()),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final (label, value) in rows) ...[
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: RichText(
              text: TextSpan(
                style: GoogleFonts.montserrat(
                  fontSize: 13,
                  height: 1.35,
                  color: AppColors.ink,
                ),
                children: [
                  TextSpan(
                    text: '$label : ',
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  TextSpan(
                    text: value,
                    style: TextStyle(
                      fontWeight: FontWeight.w500,
                      color: label == 'TAKAS' ? AppColors.gold : AppColors.ink,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

List<String> _photoUrls(Map<String, dynamic> listing) {
  final raw = listing['photo_urls'];
  if (raw is List) {
    return raw.map((e) => e.toString()).where((s) => s.isNotEmpty).toList();
  }
  return const [];
}
