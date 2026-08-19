import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/api_client.dart';
import '../../core/auth_provider.dart';
import '../../core/models.dart';

/// Konuşma listesi ekranı
class ConversationsScreen extends StatefulWidget {
  const ConversationsScreen({super.key});

  @override
  State<ConversationsScreen> createState() => _ConversationsScreenState();
}

class _ConversationsScreenState extends State<ConversationsScreen> {
  List<Conversation> _convs = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final resp = await ApiClient.get('/messages', auth: true);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (resp.ok && resp.data != null) {
        final data = resp.data as Map<String, dynamic>;
        _convs = (data['conversations'] as List)
            .map((e) => Conversation.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    if (!auth.isLoggedIn) {
      return const Scaffold(
        body: Center(child: Text('Mesajları görmek için giriş yapın.')),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Mesajlar')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _convs.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.message_outlined, size: 64, color: Colors.grey),
                      SizedBox(height: 12),
                      Text('Henüz mesajınız yok.',
                          style: TextStyle(color: Colors.grey)),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.separated(
                    itemCount: _convs.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final c = _convs[i];
                      return ListTile(
                        leading: Stack(
                          children: [
                            const CircleAvatar(
                              backgroundColor: Color(0xFF002F34),
                              child: Icon(Icons.chat_bubble_outline,
                                  color: Colors.white, size: 20),
                            ),
                            if (c.unread > 0)
                              Positioned(
                                right: 0,
                                top: 0,
                                child: Container(
                                  padding: const EdgeInsets.all(3),
                                  decoration: const BoxDecoration(
                                    color: Colors.red,
                                    shape: BoxShape.circle,
                                  ),
                                  child: Text(
                                    c.unread.toString(),
                                    style: const TextStyle(
                                        color: Colors.white, fontSize: 10),
                                  ),
                                ),
                              ),
                          ],
                        ),
                        title: Text(
                          c.listingTitle ?? 'Konuşma #${c.id}',
                          style: TextStyle(
                            fontWeight: c.unread > 0
                                ? FontWeight.w800
                                : FontWeight.w500,
                          ),
                        ),
                        onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => MessagesScreen(
                              conversationId: c.id,
                              listingTitle: c.listingTitle,
                            ),
                          ),
                        ).then((_) => _load()),
                      );
                    },
                  ),
                ),
    );
  }
}

/// Tek konuşma detayı / yeni mesaj ekranı
class MessagesScreen extends StatefulWidget {
  final int? conversationId;
  final int? listingId;
  final String? listingTitle;

  const MessagesScreen({
    super.key,
    this.conversationId,
    this.listingId,
    this.listingTitle,
  });

  @override
  State<MessagesScreen> createState() => _MessagesScreenState();
}

class _MessagesScreenState extends State<MessagesScreen> {
  final _ctrl = TextEditingController();
  final _scroll = ScrollController();
  List<Message> _messages = [];
  bool _loading = true;
  bool _sending = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    // Her 10 saniyede yeni mesaj kontrol et
    if (widget.conversationId != null) {
      _pollTimer = Timer.periodic(
        const Duration(seconds: 10),
        (_) => _load(scroll: false),
      );
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _scroll.dispose();
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool scroll = true}) async {
    if (widget.conversationId == null) {
      setState(() => _loading = false);
      return;
    }
    final resp = await ApiClient.get(
      '/messages',
      query: {'conv': widget.conversationId.toString()},
      auth: true,
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (resp.ok && resp.data != null) {
        final data = resp.data as Map<String, dynamic>;
        _messages = (data['messages'] as List)
            .map((e) => Message.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    });
    if (scroll && _messages.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(
            _scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        }
      });
    }
  }

  Future<void> _send() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() => _sending = true);
    _ctrl.clear();

    final body = <String, dynamic>{'body': text};
    if (widget.conversationId != null) {
      body['conversation_id'] = widget.conversationId;
    } else if (widget.listingId != null) {
      body['listing_id'] = widget.listingId;
    }

    final resp = await ApiClient.post('/messages', body, auth: true);
    if (!mounted) return;
    setState(() => _sending = false);
    if (resp.ok) {
      await _load();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(resp.error ?? 'Mesaj gönderilemedi.'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final me = context.watch<AuthProvider>().user;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.listingTitle ?? 'Mesaj'),
      ),
      body: Column(
        children: [
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _messages.isEmpty
                    ? const Center(
                        child: Text('İlk mesajı siz gönderin.'))
                    : ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.all(12),
                        itemCount: _messages.length,
                        itemBuilder: (_, i) => _Bubble(msg: _messages[i]),
                      ),
          ),

          // Mesaj giriş alanı
          SafeArea(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: const BoxDecoration(
                color: Colors.white,
                boxShadow: [
                  BoxShadow(
                      color: Colors.black12,
                      blurRadius: 4,
                      offset: Offset(0, -1))
                ],
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _ctrl,
                      decoration: const InputDecoration(
                        hintText: 'Mesaj yaz…',
                        border: InputBorder.none,
                        filled: false,
                      ),
                      maxLines: null,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  _sending
                      ? const SizedBox(
                          width: 36,
                          height: 36,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : IconButton(
                          icon: const Icon(Icons.send,
                              color: Color(0xFF002F34)),
                          onPressed: _send,
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

class _Bubble extends StatelessWidget {
  final Message msg;

  const _Bubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isMine = msg.isMine;
    return Align(
      alignment: isMine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.75),
        decoration: BoxDecoration(
          color: isMine ? const Color(0xFF002F34) : Colors.white,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isMine ? 16 : 4),
            bottomRight: Radius.circular(isMine ? 4 : 16),
          ),
          boxShadow: const [
            BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2))
          ],
        ),
        child: Text(
          msg.body,
          style: TextStyle(
            color: isMine ? Colors.white : Colors.black87,
            fontSize: 14,
          ),
        ),
      ),
    );
  }
}
