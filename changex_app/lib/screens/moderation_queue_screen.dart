import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';

class ModerationQueueScreen extends StatefulWidget {
  const ModerationQueueScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<ModerationQueueScreen> createState() => _ModerationQueueScreenState();
}

class _ModerationQueueScreenState extends State<ModerationQueueScreen> {
  List<dynamic> _queue = [];
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
      final q = await api.moderationQueue();
      if (!mounted) return;
      setState(() {
        _queue = q;
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

  Future<void> _decide(int id, String decision) async {
    try {
      await api.moderationDecision(id, decision, reason: 'superadmin panel');
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bgElevated,
        title: Text(
          'MODERASYON',
          style: GoogleFonts.montserrat(
            color: AppColors.gold,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
          ),
        ),
      ),
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFF171A22), AppColors.bg],
          ),
        ),
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: AppColors.gold))
            : _error != null
                ? Center(child: Text(_error!, style: const TextStyle(color: AppColors.danger)))
                : RefreshIndicator(
                    color: AppColors.gold,
                    onRefresh: _load,
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: _queue.length + 1,
                      itemBuilder: (context, i) {
                        if (i == 0) {
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const BrandMark(compact: true),
                                const SizedBox(height: 12),
                                Text(
                                  'Superadmin inceleme kuyruğu',
                                  style: GoogleFonts.montserrat(
                                    color: AppColors.muted,
                                    fontSize: 13,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '${_queue.length} kayıt',
                                  style: GoogleFonts.montserrat(
                                    color: AppColors.ink,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          );
                        }
                        final item = Map<String, dynamic>.from(_queue[i - 1] as Map);
                        final risk = item['risk_level']?.toString() ?? 'LOW';
                        return Container(
                          margin: const EdgeInsets.only(bottom: 14),
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: AppColors.bgElevated,
                            border: Border(
                              left: BorderSide(color: _riskColor(risk), width: 3),
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    risk,
                                    style: GoogleFonts.montserrat(
                                      color: _riskColor(risk),
                                      fontWeight: FontWeight.w700,
                                      fontSize: 12,
                                    ),
                                  ),
                                  const Spacer(),
                                  Text(
                                    item['ai_result']?.toString() ?? '-',
                                    style: GoogleFonts.montserrat(
                                      color: AppColors.muted,
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text(
                                item['title']?.toString() ?? '',
                                style: GoogleFonts.montserrat(
                                  color: AppColors.ink,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                item['description']?.toString() ?? '',
                                maxLines: 3,
                                overflow: TextOverflow.ellipsis,
                                style: GoogleFonts.montserrat(
                                  color: AppColors.muted,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                'AI conf: ${item['ai_confidence'] ?? '-'} · v${item['moderation_version'] ?? 1}',
                                style: GoogleFonts.montserrat(
                                  color: AppColors.muted,
                                  fontSize: 11,
                                ),
                              ),
                              const SizedBox(height: 12),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  _ActionChip(
                                    label: 'ONAYLA',
                                    color: AppColors.gold,
                                    onTap: () => _decide(item['id'] as int, 'APPROVE'),
                                  ),
                                  _ActionChip(
                                    label: 'REDDET',
                                    color: AppColors.danger,
                                    onTap: () => _decide(item['id'] as int, 'REJECT'),
                                  ),
                                  _ActionChip(
                                    label: 'DÜZENLET',
                                    color: AppColors.blue,
                                    onTap: () => _decide(item['id'] as int, 'REQUEST_EDIT'),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
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
          border: Border.all(color: color.withValues(alpha: 0.6)),
        ),
        child: Text(
          label,
          style: GoogleFonts.montserrat(
            color: color,
            fontWeight: FontWeight.w700,
            fontSize: 11,
            letterSpacing: 0.6,
          ),
        ),
      ),
    );
  }
}
