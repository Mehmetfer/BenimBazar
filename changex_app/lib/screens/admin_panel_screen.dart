import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/listing_presentation_layout.dart';
import 'admin_login_screen.dart';
import 'create_listing_screen.dart';
import 'home_screen.dart';

class AdminPanelScreen extends StatefulWidget {
  const AdminPanelScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<AdminPanelScreen> createState() => _AdminPanelScreenState();
}

class _AdminPanelScreenState extends State<AdminPanelScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  Map<String, dynamic>? _panel;
  Map<String, dynamic>? _dashboard;
  List<dynamic> _queue = [];
  List<dynamic> _staff = [];
  List<dynamic> _users = [];
  List<dynamic> _myTasks = [];
  List<dynamic> _audit = [];
  List<dynamic> _supportTickets = [];
  List<dynamic> _messageReports = [];
  List<dynamic> _listingHits = [];
  Map<String, dynamic>? _health;
  bool _loading = true;
  String? _error;
  final _userSearch = TextEditingController();
  final _listingSearch = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 6, vsync: this);
    _refreshAll();
  }

  @override
  void dispose() {
    _tabs.dispose();
    _userSearch.dispose();
    _listingSearch.dispose();
    super.dispose();
  }

  bool get _canAssignTasks =>
      widget.user['role'] == 'admin' || widget.user['role'] == 'superadmin';
  bool get _canAssignRoles => widget.user['role'] == 'superadmin';
  bool get _canViewAudit =>
      widget.user['role'] == 'admin' || widget.user['role'] == 'superadmin';
  bool get _canDeleteAnyListing =>
      widget.user['role'] == 'admin' || widget.user['role'] == 'superadmin';

  Future<void> _searchListings() async {
    try {
      final hits = await api.adminListings(q: _listingSearch.text.trim());
      if (!mounted) return;
      setState(() => _listingHits = hits);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${hits.length} sonuç')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Arama başarısız: ${e.message}')),
      );
    }
  }

  Future<void> _adminCancelListing(int id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(
          'İlanı sil',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w800),
        ),
        content: const Text(
          'Bu ilan soft-delete ile yayından kaldırılacak. Emin misiniz?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Vazgeç'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sil'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await api.cancelListing(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('İlan silindi')),
      );
      await _searchListings();
      await _refreshAll(silent: true);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    }
  }

  Future<void> _refreshAll({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final panel = await api.adminPanel();
      final queue = await api.moderationQueue();
      final tasks = await api.myAssignments();
      Map<String, dynamic>? dash;
      List<dynamic> audit = const [];
      Map<String, dynamic>? health;
      try {
        dash = await api.adminDashboard();
      } catch (_) {
        dash = null;
      }
      try {
        health = await api.health();
      } catch (_) {
        health = null;
      }
      if (_canViewAudit) {
        try {
          audit = await api.adminAudit(limit: 40);
        } catch (_) {
          audit = const [];
        }
      }
      List<dynamic> support = const [];
      List<dynamic> reports = const [];
      if (_canViewAudit) {
        try {
          support = await api.adminSupportTickets();
        } catch (_) {
          support = const [];
        }
        try {
          reports = await api.adminMessageReports();
        } catch (_) {
          reports = const [];
        }
      }
      List<dynamic> staff = const [];
      if (_canAssignTasks) {
        staff = await api.adminStaff();
      }
      if (!mounted) return;
      setState(() {
        _panel = panel;
        _dashboard = dash;
        _queue = queue;
        _myTasks = tasks;
        _staff = staff;
        _audit = audit;
        _supportTickets = support;
        _messageReports = reports;
        _health = health;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _decide(int id, String decision, {String reason = ''}) async {
    final needsConfirm = decision == 'APPROVE' ||
        decision == 'REJECT' ||
        decision == 'DELETE';
    if (needsConfirm) {
      final labels = {
        'APPROVE': 'Bu ilanı ONAYLAMAK istediğinize emin misiniz?',
        'REJECT': 'Bu ilanı REDDETMEK istediğinize emin misiniz?',
        'DELETE': 'Bu ilanı SİLMEK istediğinize emin misiniz? Bu işlem geri alınamaz.',
      };
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(
            'Onay gerekli',
            style: GoogleFonts.montserrat(fontWeight: FontWeight.w800),
          ),
          content: Text(labels[decision] ?? decision),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Vazgeç'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Onayla'),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }
    try {
      await api.moderationDecision(
        id,
        decision,
        reason: reason.isEmpty ? 'panel' : reason,
      );
      await _refreshAll(silent: true);
      if (!mounted) return;
      final labels = {
        'APPROVE': 'Onaylandı',
        'REJECT': 'Reddedildi',
        'REQUEST_EDIT': 'Düzenleme istendi',
        'DELETE': 'Silindi',
      };
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(labels[decision] ?? decision)),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('İşlem başarısız: ${e.message}'),
          action: SnackBarAction(label: 'Tekrar', onPressed: () => _decide(id, decision, reason: reason)),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('İşlem başarısız: $e')),
      );
    }
  }

  Future<void> _searchUsers() async {
    try {
      final users = await api.adminUsers(q: _userSearch.text.trim());
      if (!mounted) return;
      setState(() => _users = users);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _setRole(int userId, String role) async {
    try {
      await api.assignUserRole(userId, role);
      await _searchUsers();
      await _refreshAll();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _assignTask(int listingId, int assigneeId) async {
    try {
      await api.createAssignment(listingId: listingId, assigneeId: assigneeId);
      await _refreshAll();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Görev atandı')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Color _riskColor(String? risk) {
    switch ((risk ?? '').toUpperCase()) {
      case 'CRITICAL':
        return AppColors.danger;
      case 'HIGH':
        return const Color(0xFFE07A3D);
      case 'MEDIUM':
        return AppColors.gold;
      default:
        return AppColors.blue;
    }
  }

  @override
  Widget build(BuildContext context) {
    final role = widget.user['role']?.toString() ?? '';
    final pending = (_panel?['stats'] as Map?)?['pending_moderation'] ?? _queue.length;
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bgElevated,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'YÖNETİM PANELİ',
              style: GoogleFonts.montserrat(
                color: AppColors.gold,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2,
                fontSize: 14,
              ),
            ),
            Text(
              '${widget.user['username']} · $role · onay bekleyen: $pending',
              style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 11),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Yenile',
            onPressed: _refreshAll,
            icon: const Icon(Icons.refresh, color: AppColors.gold),
          ),
          IconButton(
            tooltip: 'Çıkış',
            onPressed: () async {
              await api.setToken(null);
              if (!context.mounted) return;
              Navigator.of(context).pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const AdminLoginScreen()),
                (_) => false,
              );
            },
            icon: const Icon(Icons.logout, color: AppColors.muted),
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          indicatorColor: AppColors.gold,
          labelColor: AppColors.gold,
          unselectedLabelColor: AppColors.muted,
          labelStyle: GoogleFonts.montserrat(
            fontWeight: FontWeight.w800,
            fontSize: 12,
          ),
          tabs: [
            const Tab(text: 'ÖZET'),
            Tab(text: 'ONAY ($pending)'),
            Tab(text: 'GÖREVLERİM (${_myTasks.length})'),
            Tab(text: 'DESTEK (${_supportTickets.length})'),
            const Tab(text: 'SİSTEM'),
            const Tab(text: 'PERSONEL'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.gold))
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, style: const TextStyle(color: AppColors.danger)),
                        const SizedBox(height: 12),
                        FilledButton(onPressed: _refreshAll, child: const Text('Tekrar dene')),
                      ],
                    ),
                  ),
                )
              : TabBarView(
                  controller: _tabs,
                  children: [
                    _buildDashboardTab(),
                    _buildQueueTab(),
                    _buildTasksTab(),
                    _buildSupportTab(),
                    _buildSystemTab(),
                    _buildStaffTab(),
                  ],
                ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.gold,
                    side: const BorderSide(color: AppColors.gold),
                  ),
                  onPressed: () {
                    Navigator.of(context)
                        .push(
                      MaterialPageRoute(
                        builder: (_) => CreateListingScreen(user: widget.user),
                      ),
                    )
                        .then((_) => _refreshAll());
                  },
                  icon: const Icon(Icons.add_a_photo_outlined),
                  label: const Text('Fotoğraflı ilan'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => HomeScreen(user: widget.user),
                      ),
                    );
                  },
                  child: Text(
                    'Uygulama',
                    style: GoogleFonts.montserrat(color: AppColors.muted),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDashboardTab() {
    final g = Map<String, dynamic>.from((_dashboard?['general'] as Map?) ?? {});
    final sec = Map<String, dynamic>.from((_dashboard?['security'] as Map?) ?? {});
    final msg = Map<String, dynamic>.from((_dashboard?['messaging'] as Map?) ?? {});
    final tiles = <(String, String)>[
      ('Kullanıcı', '${g['total_users'] ?? '—'}'),
      ('Aktif', '${g['active_users'] ?? '—'}'),
      ('İlan', '${g['total_listings'] ?? '—'}'),
      ('Pending', '${g['pending_listings'] ?? _queue.length}'),
      ('Onaylı', '${g['approved_listings'] ?? '—'}'),
      ('Red', '${g['rejected_listings'] ?? '—'}'),
      ('Silinen', '${g['deleted_listings'] ?? '—'}'),
      ('Fotoğraf', '${g['total_photos'] ?? '—'}'),
      ('Destek açık', '${msg['open_support_tickets'] ?? '—'}'),
      ('Mesaj rapor', '${msg['reported_messages'] ?? '—'}'),
      ('Konuşma', '${msg['active_conversations'] ?? '—'}'),
      ('Engelli', '${msg['blocked_users'] ?? '—'}'),
    ];
    return RefreshIndicator(
      color: AppColors.gold,
      onRefresh: _refreshAll,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'GENEL DURUM',
            style: GoogleFonts.montserrat(
              color: AppColors.gold,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.8,
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: tiles
                .map(
                  (t) => Container(
                    width: 150,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.bgElevated,
                      border: Border.all(color: AppColors.line),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          t.$1,
                          style: GoogleFonts.montserrat(
                            color: AppColors.muted,
                            fontSize: 11,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          t.$2,
                          style: GoogleFonts.montserrat(
                            fontWeight: FontWeight.w800,
                            fontSize: 20,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 20),
          Text(
            'GÜVENLİK',
            style: GoogleFonts.montserrat(
              color: AppColors.gold,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Başarısız giriş: ${sec['failed_logins_24h'] ?? '—'} · '
            'Yetkisiz: ${sec['unauthorized_attempts'] ?? '—'} · '
            'Admin işlem: ${sec['admin_actions'] ?? '—'}',
            style: GoogleFonts.montserrat(fontSize: 12, color: AppColors.muted),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _listingSearch,
            decoration: InputDecoration(
              labelText: 'İlan ara (başlık)',
              suffixIcon: IconButton(
                icon: const Icon(Icons.search, color: AppColors.gold),
                onPressed: _searchListings,
              ),
            ),
            onSubmitted: (_) => _searchListings(),
          ),
          if (_listingHits.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              'Arama sonuçları (${_listingHits.length})',
              style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            ..._listingHits.take(20).map((raw) {
              final item = Map<String, dynamic>.from(raw as Map);
              final id = _asInt(item['id']);
              final status = item['status']?.toString() ?? '';
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.bgElevated,
                  border: Border.all(color: AppColors.line),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item['title']?.toString() ?? '#$id',
                            style: GoogleFonts.montserrat(
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                          Text(
                            '#$id · $status · ${item['category'] ?? ''}',
                            style: GoogleFonts.montserrat(
                              color: AppColors.muted,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (_canDeleteAnyListing &&
                        status.toUpperCase() != 'CANCELLED' &&
                        status.toUpperCase() != 'TRADED' &&
                        status.toUpperCase() != 'RESERVED')
                      TextButton(
                        onPressed: () => _adminCancelListing(id),
                        child: Text(
                          'SİL',
                          style: GoogleFonts.montserrat(
                            color: AppColors.danger,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                  ],
                ),
              );
            }),
          ],
          const SizedBox(height: 12),
          Text(
            'Son aktiviteler',
            style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          if ((_dashboard?['recent_activity'] as List?)?.isEmpty ?? true)
            Text(
              'Henüz aktivite yok',
              style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
            )
          else
            ...((_dashboard?['recent_activity'] as List?) ?? []).take(8).map((raw) {
              final a = Map<String, dynamic>.from(raw as Map);
              return ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(
                  '${a['action']} · ${a['entity'] ?? ''} #${a['entity_id'] ?? ''}',
                  style: GoogleFonts.montserrat(fontSize: 12),
                ),
                subtitle: Text(
                  'actor=${a['actor_id']} · ${a['created_at']}',
                  style: GoogleFonts.montserrat(fontSize: 10, color: AppColors.muted),
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildSupportTab() {
    if (!_canViewAudit) {
      return Center(
        child: Text(
          'Destek merkezi için admin / superadmin gerekli',
          style: GoogleFonts.montserrat(color: AppColors.muted),
        ),
      );
    }
    return RefreshIndicator(
      color: AppColors.gold,
      onRefresh: _refreshAll,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'DESTEK MERKEZİ',
            style: GoogleFonts.montserrat(color: AppColors.gold, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          if (_supportTickets.isEmpty)
            Text('Açık destek kaydı yok', style: GoogleFonts.montserrat(color: AppColors.muted))
          else
            ..._supportTickets.map((raw) {
              final t = Map<String, dynamic>.from(raw as Map);
              return Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.bgElevated,
                  border: Border.all(color: AppColors.line),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${t['public_id']} · ${t['subject']}',
                      style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
                    ),
                    Text(
                      '${t['status']} · ${t['priority']} · user=${t['user_id']}',
                      style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: [
                        _ActionChip(
                          label: 'AÇ',
                          color: AppColors.blue,
                          onTap: () async {
                            try {
                              final full = await api.adminSupportTicket((t['id'] as num).toInt());
                              if (!mounted) return;
                              final msgs = (full['messages'] as List?) ?? [];
                              await showDialog<void>(
                                context: context,
                                builder: (ctx) => AlertDialog(
                                  title: Text('${full['public_id']}'),
                                  content: SizedBox(
                                    width: 420,
                                    child: SingleChildScrollView(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(full['subject']?.toString() ?? ''),
                                          const SizedBox(height: 12),
                                          ...msgs.map((raw) {
                                            final m = Map<String, dynamic>.from(raw as Map);
                                            return Padding(
                                              padding: const EdgeInsets.only(bottom: 8),
                                              child: Text(
                                                '${m['is_staff'] == true ? 'DESTEK' : 'KULLANICI'}: ${m['body']}',
                                                style: GoogleFonts.montserrat(fontSize: 12),
                                              ),
                                            );
                                          }),
                                        ],
                                      ),
                                    ),
                                  ),
                                  actions: [
                                    TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Kapat')),
                                  ],
                                ),
                              );
                            } on ApiException catch (e) {
                              if (!mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                            }
                          },
                        ),
                        _ActionChip(
                          label: 'YANITLA',
                          color: AppColors.gold,
                          onTap: () async {
                            final ctrl = TextEditingController();
                            final ok = await showDialog<bool>(
                              context: context,
                              builder: (ctx) => AlertDialog(
                                title: const Text('Destek yanıtı'),
                                content: TextField(controller: ctrl, maxLines: 4),
                                actions: [
                                  TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Vazgeç')),
                                  FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Gönder')),
                                ],
                              ),
                            );
                            final text = ctrl.text.trim();
                            ctrl.dispose();
                            if (ok == true && text.isNotEmpty) {
                              try {
                                await api.adminSupportReply((t['id'] as num).toInt(), text);
                                await _refreshAll(silent: true);
                              } on ApiException catch (e) {
                                if (!mounted) return;
                                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                              }
                            }
                          },
                        ),
                        _ActionChip(
                          label: 'ÇÖZ',
                          color: AppColors.blue,
                          onTap: () async {
                            try {
                              await api.adminSupportReply(
                                (t['id'] as num).toInt(),
                                'Ticket çözüldü olarak işaretlendi.',
                                resolve: true,
                              );
                              await _refreshAll(silent: true);
                            } on ApiException catch (e) {
                              if (!mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                            }
                          },
                        ),
                      ],
                    ),
                  ],
                ),
              );
            }),
          const SizedBox(height: 20),
          Text(
            'MESAJ MODERASYONU',
            style: GoogleFonts.montserrat(color: AppColors.gold, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          if (_messageReports.isEmpty)
            Text('Bildirilen mesaj yok', style: GoogleFonts.montserrat(color: AppColors.muted))
          else
            ..._messageReports.take(30).map((raw) {
              final r = Map<String, dynamic>.from(raw as Map);
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.bgElevated,
                  border: Border.all(color: AppColors.line),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'report #${r['id']} · ${r['reason']} · ${r['status']}',
                      style: GoogleFonts.montserrat(fontWeight: FontWeight.w700, fontSize: 12),
                    ),
                    Text(
                      r['body_preview']?.toString() ?? '',
                      style: GoogleFonts.montserrat(fontSize: 11, color: AppColors.muted),
                    ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 8,
                      children: [
                        _ActionChip(
                          label: 'İŞLEM',
                          color: AppColors.danger,
                          onTap: () async {
                            try {
                              await api.adminModerateMessageReport((r['id'] as num).toInt(), 'ACTIONED');
                              await _refreshAll(silent: true);
                            } on ApiException catch (e) {
                              if (!mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                            }
                          },
                        ),
                        _ActionChip(
                          label: 'REDDET',
                          color: AppColors.muted,
                          onTap: () async {
                            try {
                              await api.adminModerateMessageReport((r['id'] as num).toInt(), 'DISMISSED');
                              await _refreshAll(silent: true);
                            } on ApiException catch (e) {
                              if (!mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                            }
                          },
                        ),
                      ],
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildSystemTab() {
    final sys = Map<String, dynamic>.from((_dashboard?['system'] as Map?) ?? {});
    final storage = Map<String, dynamic>.from((sys['storage'] as Map?) ?? {});
    return RefreshIndicator(
      color: AppColors.gold,
      onRefresh: _refreshAll,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'SİSTEM SAĞLIĞI',
            style: GoogleFonts.montserrat(
              color: AppColors.gold,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 12),
          _kv('API health', _health == null ? 'UNKNOWN' : 'OK'),
          _kv('Database', (sys['database'] as Map?)?['ok'] == true ? 'OK' : '—'),
          _kv('Storage dir', storage['uploads_dir_exists'] == true ? 'OK' : 'MISSING'),
          _kv('Upload files', '${storage['upload_files'] ?? '—'}'),
          const SizedBox(height: 16),
          Text(
            'AUDIT LOG',
            style: GoogleFonts.montserrat(
              color: AppColors.gold,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          if (!_canViewAudit)
            Text(
              'Audit için admin / superadmin gerekli',
              style: GoogleFonts.montserrat(color: AppColors.muted),
            )
          else if (_audit.isEmpty)
            Text(
              'Kayıt yok',
              style: GoogleFonts.montserrat(color: AppColors.muted),
            )
          else
            ..._audit.take(30).map((raw) {
              final a = Map<String, dynamic>.from(raw as Map);
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.bgElevated,
                  border: Border.all(color: AppColors.line),
                ),
                child: Text(
                  '${a['action']} | who=${a['actor_id']} | target=${a['entity']}:${a['entity_id']} | when=${a['created_at']}',
                  style: GoogleFonts.montserrat(fontSize: 11),
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(k, style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12)),
          ),
          Text(v, style: GoogleFonts.montserrat(fontWeight: FontWeight.w700, fontSize: 12)),
        ],
      ),
    );
  }

  Widget _buildQueueTab() {
    return RefreshIndicator(
      color: AppColors.gold,
      onRefresh: _refreshAll,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _queue.isEmpty ? 2 : _queue.length + 1,
        itemBuilder: (context, i) {
          if (i == 0) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.goldSoft,
                  border: Border.all(color: AppColors.gold.withValues(alpha: 0.5)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'ONAY BEKLEYEN TAKAS İLANLARI',
                      style: GoogleFonts.montserrat(
                        color: AppColors.gold,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.8,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Burada AI ön incelemeden geçen ilanlar listelenir.\n'
                      'Her kartta: Onayla · Reddet · Düzenleme iste · Sil',
                      style: GoogleFonts.montserrat(
                        color: AppColors.ink,
                        fontSize: 12,
                        height: 1.35,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '${_queue.length} ilan onay kutusunda',
                      style: GoogleFonts.montserrat(
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }
          if (_queue.isEmpty) {
            return Padding(
              padding: const EdgeInsets.only(top: 40),
              child: Column(
                children: [
                  Icon(Icons.inbox_outlined, size: 48, color: AppColors.muted.withValues(alpha: 0.7)),
                  const SizedBox(height: 12),
                  Text(
                    'Şu an onay bekleyen ilan yok',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.montserrat(
                      color: AppColors.muted,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Kullanıcılar yeni takas kaydı oluşturunca\nburada görünecek.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
                  ),
                ],
              ),
            );
          }
          final item = Map<String, dynamic>.from(_queue[i - 1] as Map);
          return _QueueCard(
            item: item,
            riskColor: _riskColor(item['risk_level']?.toString()),
            canAssign: _canAssignTasks,
            staff: _staff,
            onDecide: _decide,
            onAssign: _assignTask,
            onPreview: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => Scaffold(
                    backgroundColor: const Color(0xFF050607),
                    appBar: AppBar(
                      backgroundColor: const Color(0xFF050607),
                      title: Text(
                        'İlan önizleme (yayın görünümü)',
                        style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
                      ),
                    ),
                    body: ListView(
                      children: [
                        ListingDetailLayout(listing: item),
                        Padding(
                          padding: const EdgeInsets.all(16),
                          child: Text(
                            'Bu önizleme kullanıcıya görünecek sunum şablonudur.',
                            style: GoogleFonts.montserrat(
                              color: AppColors.muted,
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildTasksTab() {
    if (_myTasks.isEmpty) {
      return Center(
        child: Text(
          'Size atanmış açık görev yok',
          style: GoogleFonts.montserrat(color: AppColors.muted),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: _myTasks.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        final t = Map<String, dynamic>.from(_myTasks[i] as Map);
        return Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppColors.bgElevated,
            border: Border.all(color: AppColors.line),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                t['title']?.toString() ?? 'İlan #${t['listing_id']}',
                style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                '${t['listing_status']} · ${t['category'] ?? ''}',
                style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _ActionChip(
                    label: 'ONAYLA',
                    color: AppColors.gold,
                    onTap: () => _decide(_asInt(t['listing_id']), 'APPROVE'),
                  ),
                  _ActionChip(
                    label: 'REDDET',
                    color: AppColors.danger,
                    onTap: () => _decide(_asInt(t['listing_id']), 'REJECT'),
                  ),
                  _ActionChip(
                    label: 'DÜZENLET',
                    color: AppColors.blue,
                    onTap: () => _decide(_asInt(t['listing_id']), 'REQUEST_EDIT'),
                  ),
                  _ActionChip(
                    label: 'SİL',
                    color: AppColors.muted,
                    onTap: () => _decide(_asInt(t['listing_id']), 'DELETE'),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildStaffTab() {
    if (!_canAssignTasks) {
      return Center(
        child: Text(
          'Personel yönetimi için yönetici / superadmin gerekli',
          textAlign: TextAlign.center,
          style: GoogleFonts.montserrat(color: AppColors.muted),
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Aktif personel', style: GoogleFonts.montserrat(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        ..._staff.map((raw) {
          final s = Map<String, dynamic>.from(raw as Map);
          return ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(
              s['username']?.toString() ?? '',
              style: GoogleFonts.montserrat(fontWeight: FontWeight.w600),
            ),
            subtitle: Text(
              s['role']?.toString() ?? '',
              style: GoogleFonts.montserrat(color: AppColors.gold, fontSize: 12),
            ),
          );
        }),
        if (_canAssignRoles) ...[
          const Divider(color: AppColors.line),
          Text(
            'Rol ata (Superadmin)',
            style: GoogleFonts.montserrat(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _userSearch,
                  decoration: const InputDecoration(labelText: 'Kullanıcı ara'),
                  onSubmitted: (_) => _searchUsers(),
                ),
              ),
              IconButton(
                onPressed: _searchUsers,
                icon: const Icon(Icons.search, color: AppColors.gold),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ..._users.map((raw) {
            final u = Map<String, dynamic>.from(raw as Map);
            final id = u['id'] as int;
            return Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.bgElevated,
                border: Border.all(color: AppColors.line),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${u['username']} · ${u['role']}',
                    style: GoogleFonts.montserrat(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: [
                      _ActionChip(
                        label: 'ONAYCI',
                        color: AppColors.blue,
                        onTap: () => _setRole(id, 'moderator'),
                      ),
                      _ActionChip(
                        label: 'YÖNETİCİ',
                        color: AppColors.gold,
                        onTap: () => _setRole(id, 'admin'),
                      ),
                      _ActionChip(
                        label: 'KULLANICI',
                        color: AppColors.muted,
                        onTap: () => _setRole(id, 'user'),
                      ),
                    ],
                  ),
                ],
              ),
            );
          }),
        ],
      ],
    );
  }
}

class _QueueCard extends StatelessWidget {
  const _QueueCard({
    required this.item,
    required this.riskColor,
    required this.canAssign,
    required this.staff,
    required this.onDecide,
    required this.onAssign,
    required this.onPreview,
  });

  final Map<String, dynamic> item;
  final Color riskColor;
  final bool canAssign;
  final List<dynamic> staff;
  final Future<void> Function(int id, String decision, {String reason}) onDecide;
  final Future<void> Function(int listingId, int assigneeId) onAssign;
  final VoidCallback onPreview;

  @override
  Widget build(BuildContext context) {
    final risk = item['risk_level']?.toString() ?? 'LOW';
    final assignment = item['assignment'] as Map?;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: AppColors.bgElevated,
        border: Border(left: BorderSide(color: riskColor, width: 3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListingDetailLayout(
            listing: item,
            includeGallery: true,
            galleryHeight: 180,
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      risk,
                      style: GoogleFonts.montserrat(
                        color: riskColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      item['status']?.toString() ?? '',
                      style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
                    ),
                  ],
                ),
                if (assignment != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Atanan: ${assignment['assignee_username'] ?? assignment['assignee_id']}',
                    style: GoogleFonts.montserrat(color: AppColors.gold, fontSize: 12),
                  ),
                ],
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: onPreview,
                  icon: const Icon(Icons.visibility_outlined),
                  label: const Text('İlanı İncele (yayın önizlemesi)'),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _ActionChip(
                      label: 'ONAYLA',
                      color: AppColors.gold,
                      onTap: () => onDecide(_asInt(item['id']), 'APPROVE'),
                    ),
                    _ActionChip(
                      label: 'REDDET',
                      color: AppColors.danger,
                      onTap: () => onDecide(_asInt(item['id']), 'REJECT'),
                    ),
                    _ActionChip(
                      label: 'DÜZENLET',
                      color: AppColors.blue,
                      onTap: () => onDecide(_asInt(item['id']), 'REQUEST_EDIT'),
                    ),
                    _ActionChip(
                      label: 'SİL',
                      color: AppColors.muted,
                      onTap: () => onDecide(_asInt(item['id']), 'DELETE'),
                    ),
                  ],
                ),
                if (canAssign && staff.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    'Görev ata',
                    style: GoogleFonts.montserrat(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: AppColors.muted,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final raw in staff)
                        _ActionChip(
                          label: '${raw['username']} (${raw['role']})',
                          color: AppColors.line,
                          onTap: () => onAssign(
                            _asInt(item['id']),
                            _asInt(raw['id']),
                          ),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

int _asInt(dynamic v) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.parse(v.toString());
}

class _ActionChip extends StatelessWidget {
  const _ActionChip({required this.label, required this.color, required this.onTap});

  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          border: Border.all(color: color.withValues(alpha: 0.65)),
        ),
        child: Text(
          label,
          style: GoogleFonts.montserrat(
            color: color == AppColors.line ? AppColors.ink : color,
            fontWeight: FontWeight.w700,
            fontSize: 11,
            letterSpacing: 0.5,
          ),
        ),
      ),
    );
  }
}
