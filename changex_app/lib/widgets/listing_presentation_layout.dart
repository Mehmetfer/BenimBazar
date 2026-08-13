import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../listing_presentation/presentation.dart';
import '../theme/app_theme.dart';
import 'listing_media.dart';

IconData _schemaIcon(String name) {
  switch (name) {
    case 'directions_car':
      return Icons.directions_car_outlined;
    case 'chair':
      return Icons.chair_outlined;
    case 'smartphone':
      return Icons.smartphone_outlined;
    case 'laptop':
      return Icons.laptop_outlined;
    case 'devices':
      return Icons.devices_other_outlined;
    case 'home':
      return Icons.home_outlined;
    case 'apartment':
      return Icons.apartment_outlined;
    case 'checkroom':
      return Icons.checkroom_outlined;
    case 'sports_esports':
      return Icons.sports_esports_outlined;
    default:
      return Icons.category_outlined;
  }
}

/// Feed card: photo + title + 2–3 hero stats + trade chip.
class ListingPresentationCard extends StatelessWidget {
  const ListingPresentationCard({
    super.key,
    required this.listing,
    required this.onTap,
  });

  final Map<String, dynamic> listing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final p = buildListingPresentation(listing);
    final metaCat = p.metadata.isNotEmpty ? p.metadata[0].value : '';
    final metaLoc = p.metadata.length > 2 ? p.metadata[2].value : '';
    // Media outside InkWell so horizontal photo swipe is not stolen by tap.
    return Semantics(
      button: true,
      label: '${p.title}. ${p.tradeLabel}',
      child: Material(
        color: const Color(0xFF0B0D12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ListingHeroMedia(listing: listing, height: 200, borderRadius: 0),
            InkWell(
              onTap: onTap,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(_schemaIcon(p.icon), color: const Color(0xFF3B9EFF), size: 22),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            p.title.toUpperCase(),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: GoogleFonts.montserrat(
                              fontWeight: FontWeight.w800,
                              fontSize: 15,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (p.heroStats.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        p.heroStats.take(3).map((e) => e.value).join('  ·  '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.montserrat(
                          fontSize: 11,
                          color: AppColors.muted,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Text(
                      '$metaCat · $metaLoc',
                      style: GoogleFonts.montserrat(fontSize: 11, color: AppColors.muted),
                    ),
                    const SizedBox(height: 10),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(
                        color: p.tradeOpen ? Colors.white : AppColors.bgElevated,
                        border: Border.all(
                          color: p.tradeOpen ? const Color(0xFF3B9EFF) : AppColors.line,
                        ),
                      ),
                      child: Text(
                        p.tradeLabel,
                        textAlign: TextAlign.center,
                        style: GoogleFonts.montserrat(
                          fontWeight: FontWeight.w800,
                          fontSize: 11,
                          letterSpacing: 0.6,
                          color: p.tradeOpen ? Colors.black : AppColors.gold,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Full professional detail body (gallery separate / included).
class ListingDetailLayout extends StatelessWidget {
  const ListingDetailLayout({
    super.key,
    required this.listing,
    this.includeGallery = true,
    this.galleryHeight,
    this.footer,
    this.actions,
  });

  final Map<String, dynamic> listing;
  final bool includeGallery;
  final double? galleryHeight;
  final Widget? footer;
  final Widget? actions;

  @override
  Widget build(BuildContext context) {
    final p = buildListingPresentation(listing);
    final wide = MediaQuery.sizeOf(context).width >= 720;
    final gh = galleryHeight ?? MediaQuery.sizeOf(context).width * (wide ? 0.42 : 0.95);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (includeGallery)
          ListingHeroMedia(listing: listing, height: gh, borderRadius: 0),
        Container(
          color: const Color(0xFF050607),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 52,
                    height: 52,
                    decoration: BoxDecoration(
                      border: Border.all(color: const Color(0xFF3B9EFF), width: 2),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(_schemaIcon(p.icon), color: Colors.white, size: 26),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      p.title.toUpperCase(),
                      style: GoogleFonts.montserrat(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                        height: 1.15,
                      ),
                    ),
                  ),
                ],
              ),
              if (p.heroStats.isNotEmpty) ...[
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 8,
                  children: [
                    for (var i = 0; i < p.heroStats.length && i < 3; i++) ...[
                      if (i > 0)
                        Text('|', style: GoogleFonts.montserrat(color: const Color(0xFF3B9EFF))),
                      Text(
                        p.heroStats[i].value.toUpperCase(),
                        style: GoogleFonts.montserrat(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ],
          ),
        ),
        Container(
          width: double.infinity,
          margin: const EdgeInsets.symmetric(vertical: 2),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: p.tradeOpen ? Colors.white : const Color(0xFF1A1D24),
            border: Border.symmetric(
              horizontal: BorderSide(
                color: const Color(0xFF3B9EFF),
                width: p.tradeOpen ? 2 : 1,
              ),
            ),
          ),
          child: Text(
            p.tradeLabel,
            textAlign: TextAlign.center,
            style: GoogleFonts.montserrat(
              fontWeight: FontWeight.w900,
              letterSpacing: 1.2,
              color: p.tradeOpen ? Colors.black : AppColors.gold,
            ),
          ),
        ),
        Container(
          color: const Color(0xFF050607),
          padding: const EdgeInsets.fromLTRB(8, 14, 8, 8),
          child: Row(
            children: [
              for (final m in p.metadata)
                Expanded(
                  child: Column(
                    children: [
                      Icon(
                        _metaIcon(m.key),
                        size: 18,
                        color: const Color(0xFF3B9EFF),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        m.value.toUpperCase(),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: GoogleFonts.montserrat(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                      Text(
                        m.key,
                        style: GoogleFonts.montserrat(
                          fontSize: 9,
                          color: AppColors.muted,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        Container(
          color: const Color(0xFF050607),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFF3B9EFF).withValues(alpha: 0.55)),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: wide
                  ? Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: _descBlock(p.description)),
                        const SizedBox(width: 18),
                        Expanded(child: _attrsBlock(p.attributeRows)),
                      ],
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _descBlock(p.description),
                        const SizedBox(height: 16),
                        _attrsBlock(p.attributeRows),
                      ],
                    ),
            ),
          ),
        ),
        Container(
          color: const Color(0xFF050607),
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _footerCell(
                  Icons.chat_bubble_outline,
                  'İLETİŞİM',
                  '0XXX XXX XX XX\n(Sadece uygulama içi mesajlaşma)',
                ),
              ),
              Expanded(
                child: _footerCell(
                  Icons.verified_user_outlined,
                  'GÜVENLİ TAKAS',
                  'Takaslar CHANGE X üzerinden yürütülür. Settlement/escrow henüz aktif değildir.',
                ),
              ),
              Expanded(
                child: _footerCell(
                  Icons.schedule_outlined,
                  'İLAN TARİHİ',
                  p.createdLabel.isEmpty ? '—' : p.createdLabel,
                ),
              ),
            ],
          ),
        ),
        if (actions != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: actions!,
          ),
        if (footer != null) footer!,
      ],
    );
  }

  IconData _metaIcon(String key) {
    switch (key) {
      case 'KATEGORİ':
        return Icons.home_work_outlined;
      case 'ALT KATEGORİ':
        return Icons.category_outlined;
      case 'KONUM':
        return Icons.place_outlined;
      case 'TESLİM ŞEKLİ':
        return Icons.swap_horiz;
      default:
        return Icons.info_outline;
    }
  }

  Widget _descBlock(String description) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'AÇIKLAMA',
          style: GoogleFonts.montserrat(
            color: const Color(0xFF3B9EFF),
            fontWeight: FontWeight.w800,
            letterSpacing: 1,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          description.trim().isEmpty ? 'Açıklama eklenmemiş.' : description,
          style: GoogleFonts.montserrat(color: Colors.white, height: 1.4, fontSize: 13),
        ),
      ],
    );
  }

  Widget _attrsBlock(List<PresentationStat> rows) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'ÖZELLİKLER',
          style: GoogleFonts.montserrat(
            color: const Color(0xFF3B9EFF),
            fontWeight: FontWeight.w800,
            letterSpacing: 1,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 8),
        if (rows.isEmpty)
          Text(
            'Özellik bilgisi yok.',
            style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
          )
        else
          for (final r in rows)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.label_outline, size: 14, color: const Color(0xFF3B9EFF)),
                  const SizedBox(width: 6),
                  Expanded(
                    child: RichText(
                      text: TextSpan(
                        style: GoogleFonts.montserrat(fontSize: 12, color: Colors.white),
                        children: [
                          TextSpan(
                            text: '${r.key} : ',
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                          TextSpan(text: r.value.toUpperCase()),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
      ],
    );
  }

  Widget _footerCell(IconData icon, String title, String body) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Column(
        children: [
          Icon(icon, color: const Color(0xFF3B9EFF), size: 18),
          const SizedBox(height: 4),
          Text(
            title,
            textAlign: TextAlign.center,
            style: GoogleFonts.montserrat(
              fontSize: 10,
              fontWeight: FontWeight.w800,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            body,
            textAlign: TextAlign.center,
            style: GoogleFonts.montserrat(fontSize: 10, color: AppColors.muted, height: 1.3),
          ),
        ],
      ),
    );
  }
}
