import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppColors {
  static const bg = Color(0xFF0A0F0D);
  static const bgElevated = Color(0xFF121A16);
  static const ink = Color(0xFFE8F0EA);
  static const muted = Color(0xFF8FA396);
  static const accent = Color(0xFF3DDC97);
  static const accentSoft = Color(0x333DDC97);
  static const gold = Color(0xFFD4A017);
  static const danger = Color(0xFFC45C4A);
  static const line = Color(0x223DDC97);
}

ThemeData buildChangeXTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: AppColors.bg,
    colorScheme: const ColorScheme.dark(
      surface: AppColors.bg,
      primary: AppColors.accent,
      onPrimary: AppColors.bg,
      secondary: AppColors.gold,
      onSurface: AppColors.ink,
    ),
  );

  return base.copyWith(
    textTheme: GoogleFonts.syneTextTheme(base.textTheme).apply(
      bodyColor: AppColors.ink,
      displayColor: AppColors.ink,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      titleTextStyle: GoogleFonts.syne(
        fontWeight: FontWeight.w700,
        fontSize: 20,
        color: AppColors.ink,
      ),
    ),
  );
}
