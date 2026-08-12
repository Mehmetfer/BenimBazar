import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';

class TradesScreen extends StatefulWidget {
  const TradesScreen({super.key, required this.user});

  final Map<String, dynamic> user;

  @override
  State<TradesScreen> createState() => _TradesScreenState();
}

class _TradesScreenState extends State<TradesScreen> {
  List<dynamic> _trades = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final list = await api.myTrades();
      if (!mounted) return;
      setState(() {
        _trades = list;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Takaslarım', style: GoogleFonts.syne(fontWeight: FontWeight.w700)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _trades.isEmpty
              ? Center(
                  child: Text(
                    'Henüz takas yok',
                    style: GoogleFonts.dmSans(color: AppColors.muted),
                  ),
                )
              : ListView.separated(
                  padding: const EdgeInsets.all(20),
                  itemCount: _trades.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (context, i) {
                    final t = Map<String, dynamic>.from(_trades[i] as Map);
                    final a = Map<String, dynamic>.from(t['a_value'] as Map);
                    final b = Map<String, dynamic>.from(t['b_value'] as Map);
                    return Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.bgElevated,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: AppColors.line),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Durum: ${t['state']}',
                            style: GoogleFonts.syne(fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 8),
                          Text('Karşı taraf değeri', style: GoogleFonts.dmSans(fontSize: 12, color: AppColors.muted)),
                          ValueChip(value: a),
                          const SizedBox(height: 6),
                          Text('Senin teklifin', style: GoogleFonts.dmSans(fontSize: 12, color: AppColors.muted)),
                          ValueChip(value: b),
                          if (t['exact_match'] != true) ...[
                            const SizedBox(height: 8),
                            Text(
                              'Fark gerçek para ile kapatılamaz.',
                              style: GoogleFonts.dmSans(fontSize: 12, color: AppColors.gold),
                            ),
                          ],
                        ],
                      ),
                    );
                  },
                ),
    );
  }
}
