import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// CHANGE X brand tokens (from brand guide).
class AppColors {
  static const bg = Color(0xFF0D0F14);
  static const bgElevated = Color(0xFF171A22);
  static const bgCard = Color(0xFF1F2633);
  static const ink = Color(0xFFF5F5F5);
  static const muted = Color(0xFF9AA3B2);
  static const gold = Color(0xFFD4AF37);
  static const goldSoft = Color(0x33D4AF37);
  static const blue = Color(0xFF3A7BFF);
  static const purple = Color(0xFFA855F7);
  static const danger = Color(0xFFC45C4A);
  static const line = Color(0x22D4AF37);
  static const mandal = Color(0xFFB87333); // bronze
  static const dirhem = Color(0xFFC0C0C0); // silver
  static const madalyon = Color(0xFFD4AF37); // gold
}

ThemeData buildChangeXTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: AppColors.bg,
    colorScheme: const ColorScheme.dark(
      surface: AppColors.bg,
      primary: AppColors.gold,
      onPrimary: AppColors.bg,
      secondary: AppColors.blue,
      tertiary: AppColors.purple,
      onSurface: AppColors.ink,
    ),
  );

  return base.copyWith(
    textTheme: GoogleFonts.montserratTextTheme(base.textTheme).apply(
      bodyColor: AppColors.ink,
      displayColor: AppColors.ink,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      titleTextStyle: GoogleFonts.montserrat(
        fontWeight: FontWeight.w700,
        fontSize: 18,
        color: AppColors.ink,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.gold,
        foregroundColor: AppColors.bg,
        textStyle: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.bgElevated,
      labelStyle: GoogleFonts.montserrat(color: AppColors.muted),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.gold),
      ),
    ),
  );
}
