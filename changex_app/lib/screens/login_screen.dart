import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';
import 'admin_login_screen.dart';
import 'admin_panel_screen.dart';
import 'home_screen.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.nextListingId});

  final int? nextListingId;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _obscure = true;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _userCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await api.login(_userCtrl.text.trim(), _passCtrl.text);
      await api.setToken(res['token'] as String);
      final user = Map<String, dynamic>.from(res['user'] as Map);
      if (!mounted) return;
      final role = user['role']?.toString() ?? '';
      final isStaff = {'superadmin', 'admin', 'moderator'}.contains(role);
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(
          builder: (_) => isStaff
              ? AdminPanelScreen(user: user)
              : HomeScreen(user: user),
        ),
        (_) => false,
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'Sunucuya bağlanılamadı');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0, -0.35),
            radius: 1.15,
            colors: [Color(0xFF1F2633), AppColors.bg],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 16, 24, 28),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: BrandMark()),
                    const SizedBox(height: 18),
                    Text(
                      'Takas için hesabına giriş yap',
                      textAlign: TextAlign.center,
                      style: GoogleFonts.montserrat(
                        fontSize: 14,
                        color: AppColors.muted,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const PlatformBanner(),
                    const SizedBox(height: 24),
                    TextField(
                      controller: _userCtrl,
                      autocorrect: false,
                      decoration: const InputDecoration(labelText: 'Kullanıcı adı'),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _passCtrl,
                      obscureText: _obscure,
                      onSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Şifre',
                        suffixIcon: IconButton(
                          onPressed: () =>
                              setState(() => _obscure = !_obscure),
                          icon: Icon(
                            _obscure
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                            color: AppColors.muted,
                          ),
                        ),
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _error!,
                        style: GoogleFonts.montserrat(
                          color: AppColors.danger,
                          fontSize: 13,
                        ),
                      ),
                    ],
                    const SizedBox(height: 22),
                    SizedBox(
                      height: 54,
                      child: FilledButton(
                        onPressed: _busy ? null : _submit,
                        child: Text(_busy ? 'Giriş…' : 'Giriş yap'),
                      ),
                    ),
                    TextButton(
                      onPressed: _busy
                          ? null
                          : () {
                              Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => const RegisterScreen(),
                                ),
                              );
                            },
                      child: Text(
                        'Hesabın yok mu? Kayıt ol',
                        style: GoogleFonts.montserrat(
                          color: AppColors.gold,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const AdminLoginScreen(),
                          ),
                        );
                      },
                      child: Text(
                        'Yönetim paneli girişi',
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
