import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';
import '../utils/chain_engine_ux.dart';
import '../utils/url_utils.dart';

/// Listing trade-status ribbon (Letgo/Instagram-style overlay).
///
/// CHANGE X copy (no money / no "sold"):
/// - TRADED → "Takas edilmiştir"
/// - REJECTED → "Uygun bulunmadı" (not the same as trade-closed)
/// - closed / unavailable → "Takasa kapalı"
/// - pending review → "İncelemede"
enum ListingTradeRibbon {
  none,
  exchanged,
  closed,
  rejected,
  inReview,
}

ListingTradeRibbon resolveListingRibbon(Map<String, dynamic> listing) {
  final status = (listing['status']?.toString() ?? '').toUpperCase();
  final inv = (listing['inventory_status']?.toString() ?? '').toUpperCase();
  final mod = (listing['moderation_status']?.toString() ?? '').toUpperCase();

  if (status == 'TRADED' || inv == 'TRADED') {
    return ListingTradeRibbon.exchanged;
  }

  if (status == 'REJECTED' || mod == 'REJECTED') {
    return ListingTradeRibbon.rejected;
  }

  if (status == 'PENDING_MODERATION' ||
      status == 'AI_REVIEW' ||
      status == 'ADMIN_REVIEW' ||
      status == 'MODERATION_UNAVAILABLE' ||
      status == 'ESCALATED' ||
      status == 'EDIT_REQUIRED' ||
      mod == 'PENDING' ||
      mod == 'IN_REVIEW' ||
      mod == 'EDIT_REQUIRED') {
    return ListingTradeRibbon.inReview;
  }

  if (status == 'RESERVED' ||
      inv == 'RESERVED' ||
      status == 'CANCELLED' ||
      inv == 'CANCELLED' ||
      status == 'EXPIRED' ||
      inv == 'EXPIRED' ||
      status == 'SUSPENDED' ||
      mod == 'SUSPENDED') {
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
    case ListingTradeRibbon.rejected:
      return 'UYGUN BULUNMADI';
    case ListingTradeRibbon.inReview:
      return 'İNCELEMEDE';
    case ListingTradeRibbon.none:
      return '';
  }
}

/// Full-bleed listing media with optional status ribbon across the image.
class ListingHeroMedia extends StatefulWidget {
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
  State<ListingHeroMedia> createState() => _ListingHeroMediaState();
}

class _ListingHeroMediaState extends State<ListingHeroMedia> {
  int _index = 0;
  late final PageController _page;

  @override
  void initState() {
    super.initState();
    _page = PageController();
  }

  @override
  void dispose() {
    _page.dispose();
    super.dispose();
  }

  void _go(int delta, int count) {
    if (count <= 1) return;
    final next = (_index + delta).clamp(0, count - 1);
    if (next == _index) return;
    setState(() => _index = next);
    if (!_page.hasClients) return;
    // jumpToPage is more reliable on Flutter web than animateToPage for
    // synthetic / sparse pointer events from automation tools.
    _page.jumpToPage(next);
  }

  @override
  Widget build(BuildContext context) {
    final photos = resolvePhotoUrls(widget.listing);
    final ribbon = resolveListingRibbon(widget.listing);
    final hasPhoto = photos.isNotEmpty;
    final multi = photos.length > 1;

    return ClipRRect(
      borderRadius: BorderRadius.circular(widget.borderRadius),
      child: SizedBox(
        height: widget.height,
        width: double.infinity,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (hasPhoto)
              // Mouse/trackpad swipe on Flutter web + touch
              ScrollConfiguration(
                behavior: ScrollConfiguration.of(context).copyWith(
                  dragDevices: {
                    PointerDeviceKind.touch,
                    PointerDeviceKind.mouse,
                    PointerDeviceKind.trackpad,
                    PointerDeviceKind.stylus,
                  },
                  scrollbars: false,
                ),
                child: PageView.builder(
                  controller: _page,
                  itemCount: photos.length,
                  allowImplicitScrolling: true,
                  physics: const PageScrollPhysics(
                    parent: BouncingScrollPhysics(),
                  ),
                  onPageChanged: (i) => setState(() => _index = i),
                  itemBuilder: (_, i) => Image.network(
                    photos[i],
                    fit: BoxFit.cover,
                    width: double.infinity,
                    height: widget.height,
                    gaplessPlayback: true,
                    errorBuilder: (_, __, ___) => _placeholder(),
                  ),
                ),
              )
            else
              _placeholder(),
            // Gradient must NOT steal horizontal swipes
            const IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Colors.transparent, Color(0x66000000)],
                  ),
                ),
              ),
            ),
            if (widget.showGalleryHint && multi)
              Positioned(
                top: 12,
                right: 12,
                child: IgnorePointer(
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.black54,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${_index + 1}/${photos.length}',
                      style: GoogleFonts.montserrat(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
              ),
            if (multi) ...[
              Positioned(
                left: 0,
                top: 0,
                bottom: 0,
                child: Center(
                  child: Semantics(
                    button: true,
                    label: 'Önceki fotoğraf',
                    child: IconButton(
                      constraints: const BoxConstraints(
                        minWidth: 48,
                        minHeight: 48,
                      ),
                      style: IconButton.styleFrom(
                        backgroundColor: Colors.black45,
                        foregroundColor: Colors.white,
                      ),
                      onPressed:
                          _index <= 0 ? null : () => _go(-1, photos.length),
                      icon: const Icon(Icons.chevron_left, size: 28),
                      tooltip: 'Önceki fotoğraf',
                    ),
                  ),
                ),
              ),
              Positioned(
                right: 0,
                top: 0,
                bottom: 0,
                child: Center(
                  child: Semantics(
                    button: true,
                    label: 'Sonraki fotoğraf',
                    child: IconButton(
                      constraints: const BoxConstraints(
                        minWidth: 48,
                        minHeight: 48,
                      ),
                      style: IconButton.styleFrom(
                        backgroundColor: Colors.black45,
                        foregroundColor: Colors.white,
                      ),
                      onPressed: _index >= photos.length - 1
                          ? null
                          : () => _go(1, photos.length),
                      icon: const Icon(Icons.chevron_right, size: 28),
                      tooltip: 'Sonraki fotoğraf',
                    ),
                  ),
                ),
              ),
              Positioned(
                bottom: 10,
                left: 0,
                right: 0,
                child: IgnorePointer(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      for (var i = 0; i < photos.length && i < 8; i++)
                        Container(
                          width: 6,
                          height: 6,
                          margin: const EdgeInsets.symmetric(horizontal: 3),
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color:
                                i == _index ? AppColors.gold : Colors.white54,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
            if (ribbon != ListingTradeRibbon.none)
              IgnorePointer(
                child: Center(child: TradeStatusRibbon(ribbon: ribbon)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _placeholder() {
    final category = widget.listing['category']?.toString() ?? 'Takas';
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
          Icon(_ribbonIcon(ribbon), color: Colors.white, size: 18),
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
          Icon(_ribbonIcon(ribbon), color: Colors.white, size: 18),
        ],
      ),
    );
  }

  static IconData _ribbonIcon(ListingTradeRibbon ribbon) {
    switch (ribbon) {
      case ListingTradeRibbon.exchanged:
        return Icons.check_circle_outline;
      case ListingTradeRibbon.inReview:
        return Icons.hourglass_top_outlined;
      case ListingTradeRibbon.rejected:
        return Icons.gpp_bad_outlined;
      case ListingTradeRibbon.closed:
      case ListingTradeRibbon.none:
        return Icons.block;
    }
  }
}

/// Spec strip under hero — Letgo-style quick facts (no emoji clutter).
class ListingSpecStrip extends StatelessWidget {
  const ListingSpecStrip({
    super.key,
    required this.listing,
    this.chainEngineEnabled = false,
  });

  final Map<String, dynamic> listing;
  /// From GET /api/change-chain/status — default false (production flag off).
  final bool chainEngineEnabled;

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
    final takasLabel = ChainEngineUx.takasLabel(
      chainOptIn: chainOpt,
      tradePreference: preference,
      chainEngineEnabled: chainEngineEnabled,
    );
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
  const ListingAttributeList({
    super.key,
    required this.listing,
    this.chainEngineEnabled = false,
  });

  final Map<String, dynamic> listing;
  final bool chainEngineEnabled;

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
    } else if (ribbon == ListingTradeRibbon.rejected) {
      takasValue = 'UYGUN BULUNMADI';
    } else if (ribbon == ListingTradeRibbon.inReview) {
      takasValue = 'İNCELEMEDE';
    } else if (ribbon == ListingTradeRibbon.closed) {
      takasValue = 'TAKASA KAPALI';
    } else {
      takasValue = ChainEngineUx.takasAttributeValue(
        chainOptIn: chainOpt,
        tradePreference: preference,
        chainEngineEnabled: chainEngineEnabled,
      );
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

/// Explains proposal-only vs settlement NOT_IMPLEMENTED (and flag OFF).
class ChainEngineNotice extends StatelessWidget {
  const ChainEngineNotice({
    super.key,
    required this.chainEngineEnabled,
    this.compact = false,
  });

  final bool chainEngineEnabled;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final text = chainEngineEnabled
        ? ChainEngineUx.proposalOnlyMessage()
        : ChainEngineUx.featureDisabledMessage();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8, bottom: 4),
      padding: EdgeInsets.symmetric(
        horizontal: 12,
        vertical: compact ? 8 : 12,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F0E8),
        border: Border.all(color: const Color(0xFFD9D2C3)),
      ),
      child: Text(
        text,
        style: GoogleFonts.montserrat(
          fontSize: compact ? 11 : 12,
          height: 1.35,
          fontWeight: FontWeight.w500,
          color: AppColors.ink,
        ),
      ),
    );
  }
}

List<String> resolvePhotoUrls(Map<String, dynamic> listing) {
  final raw = listing['photo_urls'] ?? listing['all_photo_urls'];
  if (raw is! List) return const [];
  return raw
      .map((e) => e.toString())
      .where((s) => s.isNotEmpty)
      .map(resolveMediaUrl)
      .toList();
}
