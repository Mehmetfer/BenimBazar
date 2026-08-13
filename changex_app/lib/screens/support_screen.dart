import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';

class SupportScreen extends StatefulWidget {
  const SupportScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<SupportScreen> createState() => _SupportScreenState();
}

class _SupportScreenState extends State<SupportScreen> {
  List<dynamic> _tickets = [];
  bool _loading = true;
  String? _error;
  final _subject = TextEditingController();
  final _body = TextEditingController();
  String _category = 'GENERAL';
  String _priority = 'NORMAL';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _subject.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await api.mySupportTickets();
      if (!mounted) return;
      setState(() {
        _tickets = items;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _create() async {
    try {
      await api.createSupportTicket(
        subject: _subject.text.trim(),
        body: _body.text.trim(),
        category: _category,
        priority: _priority,
      );
      _subject.clear();
      _body.clear();
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Destek talebi oluşturuldu')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Gönderilemedi: ${e.message}')),
      );
    }
  }

  Future<void> _openTicket(Map<String, dynamic> ticket) async {
    final reply = TextEditingController();
    try {
      final full = await api.getSupportTicket((ticket['id'] as num).toInt());
      if (!mounted) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: AppColors.bgElevated,
        builder: (ctx) {
          final messages = (full['messages'] as List?) ?? [];
          return Padding(
            padding: EdgeInsets.only(
              left: 16,
              right: 16,
              top: 16,
              bottom: MediaQuery.of(ctx).viewInsets.bottom + 16,
            ),
            child: SizedBox(
              height: MediaQuery.of(ctx).size.height * 0.7,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${full['public_id']} · ${full['status']}',
                    style: GoogleFonts.montserrat(fontWeight: FontWeight.w800, color: AppColors.gold),
                  ),
                  Text(full['subject']?.toString() ?? '', style: GoogleFonts.montserrat()),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView(
                      children: messages.map((raw) {
                        final m = Map<String, dynamic>.from(raw as Map);
                        return ListTile(
                          dense: true,
                          title: Text(m['body']?.toString() ?? ''),
                          subtitle: Text(m['is_staff'] == true ? 'CHANGE X Destek' : 'Siz'),
                        );
                      }).toList(),
                    ),
                  ),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: reply,
                          decoration: const InputDecoration(hintText: 'Yanıt yaz…'),
                        ),
                      ),
                      IconButton(
                        onPressed: () async {
                          final text = reply.text.trim();
                          if (text.isEmpty) return;
                          await api.replySupportTicket((ticket['id'] as num).toInt(), text);
                          if (ctx.mounted) Navigator.pop(ctx);
                          _load();
                        },
                        icon: const Icon(Icons.send, color: AppColors.gold),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      reply.dispose();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bgElevated,
        title: Text(
          'Destek / Bize Ulaşın',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w800, color: AppColors.gold),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Yeni talep', style: GoogleFonts.montserrat(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          TextField(controller: _subject, decoration: const InputDecoration(labelText: 'Konu')),
          const SizedBox(height: 8),
          TextField(
            controller: _body,
            minLines: 3,
            maxLines: 6,
            decoration: const InputDecoration(labelText: 'Mesaj'),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _category,
                  items: const [
                    DropdownMenuItem(value: 'GENERAL', child: Text('Genel')),
                    DropdownMenuItem(value: 'ACCOUNT', child: Text('Hesap')),
                    DropdownMenuItem(value: 'LISTING', child: Text('İlan')),
                    DropdownMenuItem(value: 'SAFETY', child: Text('Güvenlik')),
                  ],
                  onChanged: (v) => setState(() => _category = v ?? 'GENERAL'),
                  decoration: const InputDecoration(labelText: 'Kategori'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _priority,
                  items: const [
                    DropdownMenuItem(value: 'LOW', child: Text('Düşük')),
                    DropdownMenuItem(value: 'NORMAL', child: Text('Normal')),
                    DropdownMenuItem(value: 'HIGH', child: Text('Yüksek')),
                  ],
                  onChanged: (v) => setState(() => _priority = v ?? 'NORMAL'),
                  decoration: const InputDecoration(labelText: 'Öncelik'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          FilledButton(onPressed: _create, child: const Text('Gönder')),
          const SizedBox(height: 24),
          Text('Taleplerim', style: GoogleFonts.montserrat(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          if (_loading)
            const Center(child: CircularProgressIndicator(color: AppColors.gold))
          else if (_error != null)
            Column(
              children: [
                Text(_error!, style: const TextStyle(color: AppColors.danger)),
                FilledButton(onPressed: _load, child: const Text('Tekrar dene')),
              ],
            )
          else if (_tickets.isEmpty)
            Text('Henüz destek talebiniz yok.', style: GoogleFonts.montserrat(color: AppColors.muted))
          else
            ..._tickets.map((raw) {
              final t = Map<String, dynamic>.from(raw as Map);
              return ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('${t['public_id']} · ${t['subject']}'),
                subtitle: Text('${t['status']} · ${t['priority']}'),
                onTap: () => _openTicket(t),
              );
            }),
        ],
      ),
    );
  }
}
