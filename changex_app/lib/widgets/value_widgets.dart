import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';

class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.compact = false});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'CHANGE ',
              style: GoogleFonts.montserrat(
                fontSize: compact ? 22 : 34,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2,
                color: AppColors.ink,
              ),
            ),
            Text(
              'X',
              style: GoogleFonts.montserrat(
                fontSize: compact ? 22 : 34,
                fontWeight: FontWeight.w900,
                color: AppColors.gold,
              ),
            ),
          ],
        ),
        if (!compact)
          Text(
            'TAKAS EKOSİSTEMİ',
            style: GoogleFonts.montserrat(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 2.2,
              color: AppColors.gold,
            ),
          ),
      ],
    );
  }
}

class PlatformBanner extends StatelessWidget {
  const PlatformBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.goldSoft,
        border: Border.all(color: AppColors.gold.withValues(alpha: 0.45)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Text(
            'SAHİP OLDUĞUNLA, İSTEDİĞİNE ULAŞ.',
            textAlign: TextAlign.center,
            style: GoogleFonts.montserrat(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.4,
              color: AppColors.ink,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Paran değil, değerin konuşur. · PARA YOK · SADECE TAKAS',
            textAlign: TextAlign.center,
            style: GoogleFonts.montserrat(
              fontSize: 10,
              fontWeight: FontWeight.w500,
              color: AppColors.muted,
            ),
          ),
        ],
      ),
    );
  }
}

class PillarsRow extends StatelessWidget {
  const PillarsRow({super.key});

  static const _items = [
    ('SADECE TAKAS', 'Para yok'),
    ('GÜVENLİ', 'Doğrulanmış'),
    ('ZİNCİR', 'Çoklu takas'),
    ('DEĞERİN VAR', 'Ürün değeri'),
  ];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 72,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: _items.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final (title, sub) = _items[i];
          return Container(
            width: 118,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.bgCard,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.line),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: GoogleFonts.montserrat(
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    color: AppColors.gold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  sub,
                  style: GoogleFonts.montserrat(
                    fontSize: 10,
                    color: AppColors.muted,
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class ValueChip extends StatelessWidget {
  const ValueChip({super.key, required this.value, this.dense = false});

  final Map<String, dynamic> value;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final m = value['madalyon'] ?? 0;
    final d = value['dirhem'] ?? 0;
    final n = value['mandal'] ?? 0;
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        _UnitBadge(label: '$m MADALYON', color: AppColors.madalyon),
        _UnitBadge(label: '$d DİRHEM', color: AppColors.dirhem),
        _UnitBadge(label: '$n MANDAL', color: AppColors.mandal),
      ],
    );
  }
}

class _UnitBadge extends StatelessWidget {
  const _UnitBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(
        label,
        style: GoogleFonts.montserrat(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

class BalanceChip extends StatelessWidget {
  const BalanceChip({super.key, required this.totalMandal});

  final int totalMandal;

  @override
  Widget build(BuildContext context) {
    // Display primarily in Dirhem for guide parity.
    final dirhem = totalMandal ~/ 254;
    final rem = totalMandal % 254;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.bgElevated,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            'DEĞER BAKİYE',
            style: GoogleFonts.montserrat(
              fontSize: 8,
              fontWeight: FontWeight.w700,
              letterSpacing: 1,
              color: AppColors.gold,
            ),
          ),
          Text(
            '$dirhem.${rem.toString().padLeft(3, '0')} DİRHEM',
            style: GoogleFonts.montserrat(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: AppColors.ink,
            ),
          ),
        ],
      ),
    );
  }
}
