import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import 'chat_detail_screen.dart';
import 'support_screen.dart';

class MessagesInboxScreen extends StatefulWidget {
  const MessagesInboxScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<MessagesInboxScreen> createState() => _MessagesInboxScreenState();
}

class _MessagesInboxScreenState extends State<MessagesInboxScreen> {
  List<dynamic> _items = [];
  int _unread = 0;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final inbox = await api.messagesInbox();
      final unread = await api.messagesUnreadCount();
      if (!mounted) return;
      setState(() {
        _items = inbox;
        _unread = unread;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bgElevated,
        title: Text(
          _unread > 0 ? 'Mesajlar ($_unread)' : 'Mesajlar',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w800, color: AppColors.gold),
        ),
        actions: [
          IconButton(
            tooltip: 'Destek',
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => SupportScreen(user: widget.user)),
              );
            },
            icon: const Icon(Icons.support_agent, color: AppColors.gold),
          ),
          IconButton(
            onPressed: _load,
            icon: const Icon(Icons.refresh, color: AppColors.muted),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.gold))
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('Mesajlar yüklenemedi', style: GoogleFonts.montserrat(color: AppColors.danger)),
                      const SizedBox(height: 8),
                      Text(_error!, style: GoogleFonts.montserrat(fontSize: 12, color: AppColors.muted)),
                      const SizedBox(height: 12),
                      FilledButton(onPressed: _load, child: const Text('Tekrar dene')),
                    ],
                  ),
                )
              : _items.isEmpty
                  ? Center(
                      child: Text(
                        'Henüz mesajınız yok.\nİlanlardan satıcıya mesaj gönderebilirsiniz.',
                        textAlign: TextAlign.center,
                        style: GoogleFonts.montserrat(color: AppColors.muted),
                      ),
                    )
                  : RefreshIndicator(
                      color: AppColors.gold,
                      onRefresh: _load,
                      child: ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: _items.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (context, i) {
                          final c = Map<String, dynamic>.from(_items[i] as Map);
                          final peer = Map<String, dynamic>.from(c['peer'] as Map? ?? {});
                          final last = Map<String, dynamic>.from(c['last_message'] as Map? ?? {});
                          final unread = (c['unread_count'] as num?)?.toInt() ?? 0;
                          return InkWell(
                            onTap: () async {
                              await Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => ChatDetailScreen(
                                    user: widget.user,
                                    conversation: c,
                                  ),
                                ),
                              );
                              _load();
                            },
                            child: Container(
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: AppColors.bgElevated,
                                border: Border.all(color: AppColors.line),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          peer['username']?.toString() ?? 'Kullanıcı',
                                          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
                                        ),
                                      ),
                                      if (unread > 0)
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                          color: AppColors.gold,
                                          child: Text(
                                            '$unread',
                                            style: GoogleFonts.montserrat(
                                              fontWeight: FontWeight.w800,
                                              fontSize: 11,
                                              color: Colors.black,
                                            ),
                                          ),
                                        ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    c['listing_title']?.toString() ?? 'İlan #${c['listing_id']}',
                                    style: GoogleFonts.montserrat(color: AppColors.gold, fontSize: 12),
                                  ),
                                  const SizedBox(height: 6),
                                  Text(
                                    last['body']?.toString() ?? 'Konuşma başladı',
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
