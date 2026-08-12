import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import 'home_screen.dart';
import 'login_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..forward();
    _boot();
  }

  Future<void> _boot() async {
    Map<String, dynamic>? user;
    try {
      user = await api.me();
    } catch (_) {
      user = null;
    }
    await Future<void>.delayed(const Duration(milliseconds: 1400));
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder<void>(
        transitionDuration: const Duration(milliseconds: 450),
        pageBuilder: (_, anim, __) => FadeTransition(
          opacity: anim,
          child: HomeScreen(user: user),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0, -0.25),
            radius: 1.1,
            colors: [Color(0xFF143528), AppColors.bg],
          ),
        ),
        child: SafeArea(
          child: FadeTransition(
            opacity: _controller,
            child: Column(
              children: [
                const Spacer(flex: 3),
                Text(
                  'CHANGE X',
                  style: GoogleFonts.syne(
                    fontSize: 42,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 3,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  'Sadece takas',
                  style: GoogleFonts.dmSans(
                    fontSize: 16,
                    color: AppColors.muted,
                  ),
                ),
                const SizedBox(height: 18),
                Text(
                  'Mandal · Dirhem · Madalyon',
                  style: GoogleFonts.dmSans(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppColors.accent,
                  ),
                ),
                const Spacer(flex: 4),
                TextButton(
                  onPressed: () {
                    Navigator.of(context).pushReplacement(
                      MaterialPageRoute(builder: (_) => const LoginScreen()),
                    );
                  },
                  child: Text(
                    'Giriş / Kayıt',
                    style: GoogleFonts.dmSans(color: AppColors.gold),
                  ),
                ),
                const SizedBox(height: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
