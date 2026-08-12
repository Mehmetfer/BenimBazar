import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';

class ValueChip extends StatelessWidget {
  const ValueChip({super.key, required this.value});

  final Map<String, dynamic> value;

  @override
  Widget build(BuildContext context) {
    final m = value['madalyon'] ?? 0;
    final d = value['dirhem'] ?? 0;
    final n = value['mandal'] ?? 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.4)),
      ),
      child: Text(
        '$m Madalyon · $d Dirhem · $n Mandal',
        style: GoogleFonts.dmSans(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          color: AppColors.accent,
        ),
      ),
    );
  }
}

class PlatformBanner extends StatelessWidget {
  const PlatformBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.45)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        'PARA YOK · SATIN ALMA YOK · SADECE TAKAS  ·  Mandal / Dirhem / Madalyon',
        textAlign: TextAlign.center,
        style: GoogleFonts.dmSans(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.3,
          color: AppColors.ink,
        ),
      ),
    );
  }
}
