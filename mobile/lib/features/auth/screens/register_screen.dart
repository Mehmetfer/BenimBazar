import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/auth_provider.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey  = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _cityCtrl  = TextEditingController();
  final _passCtrl  = TextEditingController();
  final _pass2Ctrl = TextEditingController();
  bool _obscure = true;
  String _country = 'tr';

  @override
  void dispose() {
    for (final c in [_nameCtrl, _emailCtrl, _phoneCtrl, _cityCtrl, _passCtrl, _pass2Ctrl]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final auth = context.read<AuthProvider>();
    final err = await auth.register(
      username: _nameCtrl.text.trim(),
      password: _passCtrl.text,
      email: _emailCtrl.text.trim(),
      phone: _phoneCtrl.text.trim(),
      city: _cityCtrl.text.trim(),
      country: _country,
    );
    if (!mounted) return;
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(err), backgroundColor: Colors.red.shade700),
      );
      return;
    }
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return Scaffold(
      appBar: AppBar(title: const Text('Kayıt ol')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Ülke seçimi
              const Text('Ülke / Bölge *',
                  style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              Row(
                children: [
                  _countryChip('tr', '🇹🇷 Türkiye'),
                  const SizedBox(width: 10),
                  _countryChip('kktc', '🇨🇾 KKTC'),
                ],
              ),
              const SizedBox(height: 16),

              _field(_nameCtrl, 'Kullanıcı adı *', Icons.person_outline,
                  validator: (v) => (v == null || v.trim().length < 3)
                      ? 'En az 3 karakter'
                      : null),
              _field(_emailCtrl, 'E-posta *', Icons.email_outlined,
                  type: TextInputType.emailAddress,
                  validator: (v) => (v == null || !v.contains('@'))
                      ? 'Geçerli e-posta girin'
                      : null),
              _field(_phoneCtrl, 'GSM *', Icons.phone_outlined,
                  type: TextInputType.phone,
                  validator: (v) {
                    final d = v?.replaceAll(RegExp(r'\D'), '') ?? '';
                    return d.length < 10 ? 'Geçerli numara girin' : null;
                  }),
              _field(_cityCtrl, 'Şehir *', Icons.location_city_outlined,
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Şehir gerekli' : null),
              TextFormField(
                controller: _passCtrl,
                obscureText: _obscure,
                decoration: InputDecoration(
                  labelText: 'Şifre *',
                  prefixIcon: const Icon(Icons.lock_outline),
                  suffixIcon: IconButton(
                    icon: Icon(_obscure
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined),
                    onPressed: () => setState(() => _obscure = !_obscure),
                  ),
                ),
                validator: (v) =>
                    (v == null || v.length < 6) ? 'En az 6 karakter' : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _pass2Ctrl,
                obscureText: _obscure,
                decoration: const InputDecoration(
                  labelText: 'Şifre tekrar *',
                  prefixIcon: Icon(Icons.lock_outline),
                ),
                validator: (v) =>
                    v != _passCtrl.text ? 'Şifreler eşleşmiyor' : null,
              ),
              const SizedBox(height: 24),
              auth.loading
                  ? const Center(child: CircularProgressIndicator())
                  : ElevatedButton(
                      onPressed: _submit,
                      child: const Text('Kayıt ol'),
                    ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _countryChip(String value, String label) {
    final selected = _country == value;
    return GestureDetector(
      onTap: () => setState(() => _country = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF002F34) : Colors.white,
          border: Border.all(
            color: selected ? const Color(0xFF002F34) : const Color(0xFFDDE0E5),
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.white : Colors.black87,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _field(
    TextEditingController ctrl,
    String label,
    IconData icon, {
    TextInputType type = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextFormField(
        controller: ctrl,
        keyboardType: type,
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: Icon(icon),
        ),
        validator: validator,
      ),
    );
  }
}
