import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';

class ChatDetailScreen extends StatefulWidget {
  const ChatDetailScreen({
    super.key,
    required this.user,
    required this.conversation,
  });

  final Map<String, dynamic> user;
  final Map<String, dynamic> conversation;

  @override
  State<ChatDetailScreen> createState() => _ChatDetailScreenState();
}

class _ChatDetailScreenState extends State<ChatDetailScreen> {
  final _controller = TextEditingController();
  List<dynamic> _messages = [];
  bool _loading = true;
  bool _sending = false;
  String? _error;

  int get _cid => (widget.conversation['id'] as num).toInt();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final msgs = await api.conversationMessages(_cid);
      if (!mounted) return;
      setState(() {
        _messages = msgs;
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

  Future<void> _send({bool ack = false}) async {
    final text = _controller.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      await api.sendConversationMessage(_cid, text, acknowledgeContactWarning: ack);
      _controller.clear();
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.message.contains('iletişim') || e.message.toLowerCase().contains('contact')) {
        final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Uyarı'),
            content: Text(
              'Telefon numarası gibi görünen iletişim bilgileri tespit edildi.\n\n${e.message}',
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Düzenle')),
              FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Yine de gönder')),
            ],
          ),
        );
        if (ok == true) {
          await _send(ack: true);
        }
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Mesaj gönderilemedi: ${e.message}'),
            action: SnackBarAction(label: 'Tekrar', onPressed: () => _send(ack: ack)),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Mesaj gönderilemedi: $e')),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _report(int messageId) async {
    try {
      await api.reportMessage(messageId, 'OTHER');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Mesaj bildirildi')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _blockPeer() async {
    final peer = Map<String, dynamic>.from(widget.conversation['peer'] as Map? ?? {});
    final pid = peer['id'];
    if (pid == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Kullanıcıyı engelle'),
        content: Text('${peer['username']} engellensin mi?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Vazgeç')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Engelle')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.blockUser((pid as num).toInt());
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Kullanıcı engellendi')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final peer = Map<String, dynamic>.from(widget.conversation['peer'] as Map? ?? {});
    final title = peer['username']?.toString() ?? 'Sohbet';
    final listing = widget.conversation['listing_title']?.toString();
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bgElevated,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: GoogleFonts.montserrat(fontWeight: FontWeight.w800, fontSize: 14)),
            if (listing != null)
              Text(listing, style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 11)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Engelle',
            onPressed: _blockPeer,
            icon: const Icon(Icons.block, color: AppColors.danger),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: AppColors.gold))
                : _error != null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text('Mesajlar yüklenemedi', style: TextStyle(color: AppColors.danger)),
                            FilledButton(onPressed: _load, child: const Text('Tekrar dene')),
                          ],
                        ),
                      )
                    : _messages.isEmpty
                        ? Center(
                            child: Text(
                              'Henüz mesaj yok. İlk mesajı siz gönderin.',
                              style: GoogleFonts.montserrat(color: AppColors.muted),
                            ),
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: _messages.length,
                            itemBuilder: (context, i) {
                              final m = Map<String, dynamic>.from(_messages[i] as Map);
                              final mine = m['sender_id'].toString() == widget.user['id'].toString();
                              return Align(
                                alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
                                child: Container(
                                  margin: const EdgeInsets.only(bottom: 8),
                                  padding: const EdgeInsets.all(12),
                                  constraints: BoxConstraints(
                                    maxWidth: MediaQuery.of(context).size.width * 0.75,
                                  ),
                                  decoration: BoxDecoration(
                                    color: mine ? AppColors.goldSoft : AppColors.bgElevated,
                                    border: Border.all(color: AppColors.line),
                                  ),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        m['body']?.toString() ?? '',
                                        style: GoogleFonts.montserrat(fontSize: 13),
                                      ),
                                      const SizedBox(height: 4),
                                      Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Text(
                                            m['status']?.toString() ?? '',
                                            style: GoogleFonts.montserrat(
                                              fontSize: 10,
                                              color: AppColors.muted,
                                            ),
                                          ),
                                          if (!mine) ...[
                                            const SizedBox(width: 8),
                                            GestureDetector(
                                              onTap: () => _report((m['id'] as num).toInt()),
                                              child: Text(
                                                'Bildir',
                                                style: GoogleFonts.montserrat(
                                                  fontSize: 10,
                                                  color: AppColors.danger,
                                                ),
                                              ),
                                            ),
                                          ],
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      minLines: 1,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        hintText: 'Mesaj yaz… (telefon gerekmez)',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: _sending ? null : () => _send(),
                    icon: Icon(
                      Icons.send,
                      color: _sending ? AppColors.muted : AppColors.gold,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
