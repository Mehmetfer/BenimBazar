import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';
import 'admin_panel_screen.dart';
import 'home_screen.dart';

/// Separate giriş kapısı — kullanıcı uygulamasından bağımsız yönetim paneli.
class AdminLoginScreen extends StatefulWidget {
  const AdminLoginScreen({super.key});

  @override
  State<AdminLoginScreen> createState() => _AdminLoginScreenState();
}

class _AdminLoginScreenState extends State<AdminLoginScreen> {
  final _user = TextEditingController(text: 'superadmin');
  final _pass = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

    Future<void> _login() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await api.login(_user.text.trim(), _pass.text);
      final token = res['token']?.toString();
      if (token == null || token.isEmpty) {
        setState(() => _error = 'Oturum token alınamadı');
        return;
      }
      await api.setToken(token);
      final me = await api.me();
      final user = me ??
          (res['user'] is Map
              ? Map<String, dynamic>.from(res['user'] as Map)
              : null);
      if (user == null) {
        setState(() => _error = 'Oturum açılamadı');
        return;
      }
      final role = user['role']?.toString() ?? '';
      if (!{'superadmin', 'admin', 'moderator'}.contains(role)) {
        await api.setToken(null);
        setState(() =>
            _error = 'Bu hesap yönetim paneline giremez (rol: $role)');
        return;
      }
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => AdminPanelScreen(user: user)),
        (_) => false,
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = 'Sunucuya bağlanılamadı');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF12151C), AppColors.bg, Color(0xFF1A1520)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const BrandMark(),
                    const SizedBox(height: 8),
                    Text(
                      'YÖNETİM PANELİ',
                      textAlign: TextAlign.center,
                      style: GoogleFonts.montserrat(
                        color: AppColors.gold,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Onay kutusu · görev atama · personel',
                      textAlign: TextAlign.center,
                      style: GoogleFonts.montserrat(
                        color: AppColors.muted,
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 28),
                    TextField(
                      controller: _user,
                      decoration: const InputDecoration(labelText: 'Kullanıcı adı'),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _pass,
                      obscureText: true,
                      onSubmitted: (_) => _busy ? null : _login(),
                      decoration: const InputDecoration(labelText: 'Şifre'),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _error!,
                        style: GoogleFonts.montserrat(color: AppColors.danger),
                      ),
                    ],
                    const SizedBox(height: 20),
                    SizedBox(
                      height: 52,
                      child: FilledButton(
                        onPressed: _busy ? null : _login,
                        child: Text(_busy ? 'Giriş…' : 'Panele gir'),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: () {
                        Navigator.of(context).pushAndRemoveUntil(
                          MaterialPageRoute(
                            builder: (_) => const HomeScreen(user: null),
                          ),
                          (_) => false,
                        );
                      },
                      child: Text(
                        'Kullanıcı uygulamasına dön',
                        style: GoogleFonts.montserrat(color: AppColors.muted),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
