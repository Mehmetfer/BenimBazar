import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/api_client.dart';
import '../../core/auth_provider.dart';
import '../auth/screens/login_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _cityCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final user = context.read<AuthProvider>().user;
    _cityCtrl.text = user?.city ?? '';
    _phoneCtrl.text = user?.phone ?? '';
  }

  @override
  void dispose() {
    _cityCtrl.dispose();
    _phoneCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final resp = await ApiClient.patch('/user/profile', {
      'city': _cityCtrl.text.trim(),
      'phone': _phoneCtrl.text.trim(),
    });
    if (!mounted) return;
    setState(() => _saving = false);
    if (resp.ok) {
      await context.read<AuthProvider>().refreshMe();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profil güncellendi.')),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(resp.error ?? 'Güncelleme başarısız.')),
      );
    }
  }

  Future<void> _changePassword() async {
    final currCtrl = TextEditingController();
    final newCtrl  = TextEditingController();

    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Şifre Değiştir'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: currCtrl,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Mevcut şifre'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: newCtrl,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Yeni şifre'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('İptal')),
          ElevatedButton(
            onPressed: () async {
              Navigator.pop(context);
              final resp = await ApiClient.post(
                '/user/profile',
                {
                  'current_password': currCtrl.text,
                  'new_password': newCtrl.text,
                },
                auth: true,
              );
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                      resp.ok ? 'Şifre değiştirildi.' : (resp.error ?? 'Hata')),
                  backgroundColor: resp.ok ? Colors.green : Colors.red,
                ),
              );
            },
            child: const Text('Değiştir'),
          ),
        ],
      ),
    );

    currCtrl.dispose();
    newCtrl.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    if (!auth.isLoggedIn) {
      return Scaffold(
        appBar: AppBar(title: const Text('Profil')),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.person_outline, size: 72, color: Colors.grey),
              const SizedBox(height: 16),
              const Text('Profilini görmek için giriş yap.',
                  style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                ),
                child: const Text('Giriş Yap'),
              ),
            ],
          ),
        ),
      );
    }

    final user = auth.user!;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profilim'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (_) => AlertDialog(
                  title: const Text('Çıkış yap'),
                  content: const Text('Oturumu kapatmak istiyor musunuz?'),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('İptal')),
                    ElevatedButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('Çıkış')),
                  ],
                ),
              );
              if (confirm == true && mounted) {
                await context.read<AuthProvider>().logout();
              }
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            // Avatar
            CircleAvatar(
              radius: 40,
              backgroundColor: const Color(0xFF002F34),
              child: Text(
                user.username.substring(0, 1).toUpperCase(),
                style: const TextStyle(
                    fontSize: 32,
                    color: Colors.white,
                    fontWeight: FontWeight.w800),
              ),
            ),
            const SizedBox(height: 12),
            Text(user.username,
                style: const TextStyle(
                    fontSize: 20, fontWeight: FontWeight.w800)),
            Text(user.email ?? '',
                style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 4),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFF002F34).withAlpha(20),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                user.role == 'admin' ? '⭐ Admin' : '👤 Üye',
                style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF002F34)),
              ),
            ),
            const SizedBox(height: 24),
            const Divider(),

            // Profil düzenleme
            const Align(
              alignment: Alignment.centerLeft,
              child: Text('Bilgileri Güncelle',
                  style: TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 16)),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _phoneCtrl,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'GSM',
                prefixIcon: Icon(Icons.phone_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _cityCtrl,
              decoration: const InputDecoration(
                labelText: 'Şehir',
                prefixIcon: Icon(Icons.location_city_outlined),
              ),
            ),
            const SizedBox(height: 16),
            _saving
                ? const CircularProgressIndicator()
                : ElevatedButton(
                    onPressed: _save,
                    child: const Text('Kaydet'),
                  ),
            const SizedBox(height: 16),
            const Divider(),

            // Şifre değiştir
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.lock_outline),
              title: const Text('Şifre Değiştir'),
              trailing: const Icon(Icons.chevron_right),
              onTap: _changePassword,
            ),
          ],
        ),
      ),
    );
  }
}
