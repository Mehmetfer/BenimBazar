import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';
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
  bool _navigated = false;

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
      user = await api.me().timeout(const Duration(milliseconds: 800), onTimeout: () => null);
    } catch (_) {
      user = null;
    }
    await Future<void>.delayed(const Duration(milliseconds: 900));
    if (!mounted || _navigated) return;
    _navigated = true;
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
            center: Alignment(0, -0.3),
            radius: 1.15,
            colors: [Color(0xFF1F2633), AppColors.bg],
          ),
        ),
        child: SafeArea(
          child: FadeTransition(
            opacity: _controller,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: Column(
                children: [
                  const Spacer(flex: 3),
                  const BrandMark(),
                  const SizedBox(height: 22),
                  Text(
                    'SAHİP OLDUĞUNLA,\nİSTEDİĞİNE ULAŞ.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.montserrat(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      height: 1.25,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Paran değil, değerin konuşur.',
                    style: GoogleFonts.montserrat(
                      fontSize: 14,
                      color: AppColors.gold,
                      fontWeight: FontWeight.w600,
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
                      style: GoogleFonts.montserrat(color: AppColors.gold),
                    ),
                  ),
                  const SizedBox(height: 18),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
