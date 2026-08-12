import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/listing_media.dart';
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
  List<dynamic> _queue = [];
  List<dynamic> _staff = [];
  List<dynamic> _users = [];
  List<dynamic> _myTasks = [];
  bool _loading = true;
  String? _error;
  final _userSearch = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _refreshAll();
  }

  @override
  void dispose() {
    _tabs.dispose();
    _userSearch.dispose();
    super.dispose();
  }

  bool get _canAssignTasks =>
      widget.user['role'] == 'admin' || widget.user['role'] == 'superadmin';
  bool get _canAssignRoles => widget.user['role'] == 'superadmin';

  Future<void> _refreshAll() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final panel = await api.adminPanel();
      final queue = await api.moderationQueue();
      final tasks = await api.myAssignments();
      List<dynamic> staff = const [];
      if (_canAssignTasks) {
        staff = await api.adminStaff();
      }
      if (!mounted) return;
      setState(() {
        _panel = panel;
        _queue = queue;
        _myTasks = tasks;
        _staff = staff;
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

  Future<void> _decide(int id, String decision, {String reason = ''}) async {
    try {
      await api.moderationDecision(
        id,
        decision,
        reason: reason.isEmpty ? 'panel' : reason,
      );
      await _refreshAll();
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
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
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
          indicatorColor: AppColors.gold,
          labelColor: AppColors.gold,
          unselectedLabelColor: AppColors.muted,
          labelStyle: GoogleFonts.montserrat(
            fontWeight: FontWeight.w800,
            fontSize: 11,
          ),
          tabs: [
            Tab(text: 'ONAY ($pending)'),
            Tab(text: 'GÖREVLERİM (${_myTasks.length})'),
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
                    _buildQueueTab(),
                    _buildTasksTab(),
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
                    onTap: () => _decide(t['listing_id'] as int, 'APPROVE'),
                  ),
                  _ActionChip(
                    label: 'REDDET',
                    color: AppColors.danger,
                    onTap: () => _decide(t['listing_id'] as int, 'REJECT'),
                  ),
                  _ActionChip(
                    label: 'DÜZENLET',
                    color: AppColors.blue,
                    onTap: () => _decide(t['listing_id'] as int, 'REQUEST_EDIT'),
                  ),
                  _ActionChip(
                    label: 'SİL',
                    color: AppColors.muted,
                    onTap: () => _decide(t['listing_id'] as int, 'DELETE'),
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
  });

  final Map<String, dynamic> item;
  final Color riskColor;
  final bool canAssign;
  final List<dynamic> staff;
  final Future<void> Function(int id, String decision, {String reason}) onDecide;
  final Future<void> Function(int listingId, int assigneeId) onAssign;

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
          ListingHeroMedia(listing: item, height: 160, borderRadius: 0),
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
                const SizedBox(height: 8),
                Text(
                  item['title']?.toString() ?? '',
                  style: GoogleFonts.montserrat(fontWeight: FontWeight.w700, fontSize: 16),
                ),
                const SizedBox(height: 6),
                Text(
                  item['description']?.toString() ?? '',
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 13),
                ),
                if (assignment != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Atanan: ${assignment['assignee_username'] ?? assignment['assignee_id']}',
                    style: GoogleFonts.montserrat(color: AppColors.gold, fontSize: 12),
                  ),
                ],
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _ActionChip(
                      label: 'ONAYLA',
                      color: AppColors.gold,
                      onTap: () => onDecide(item['id'] as int, 'APPROVE'),
                    ),
                    _ActionChip(
                      label: 'REDDET',
                      color: AppColors.danger,
                      onTap: () => onDecide(item['id'] as int, 'REJECT'),
                    ),
                    _ActionChip(
                      label: 'DÜZENLET',
                      color: AppColors.blue,
                      onTap: () => onDecide(item['id'] as int, 'REQUEST_EDIT'),
                    ),
                    _ActionChip(
                      label: 'SİL',
                      color: AppColors.muted,
                      onTap: () => onDecide(item['id'] as int, 'DELETE'),
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
                          onTap: () => onAssign(item['id'] as int, raw['id'] as int),
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
