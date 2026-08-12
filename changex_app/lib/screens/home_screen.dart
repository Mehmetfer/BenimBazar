import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/value_widgets.dart';
import 'create_listing_screen.dart';
import 'listing_detail_screen.dart';
import 'login_screen.dart';
import 'trades_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.user});

  final Map<String, dynamic>? user;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _search = TextEditingController();
  List<dynamic> _listings = [];
  bool _loading = true;
  String? _error;
  String? _category;
  int _balanceMandal = 0;

  static const categories = [
    'Lobi',
    'Elektronik',
    'Spor',
    'Ev',
    'Kitap',
    'Moda',
    'Diğer',
  ];

  @override
  void initState() {
    super.initState();
    _category = 'Lobi';
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await api.listings(
        q: _search.text.trim(),
        category: _category == null || _category == 'Lobi' ? null : _category,
      );
      var bal = 0;
      for (final raw in list) {
        final item = Map<String, dynamic>.from(raw as Map);
        final owner = Map<String, dynamic>.from(item['owner'] as Map? ?? {});
        if (widget.user != null &&
            owner['username'] == widget.user!['username']) {
          final value = Map<String, dynamic>.from(item['value'] as Map? ?? {});
          bal += (value['total_mandal'] as num?)?.toInt() ?? 0;
        }
      }
      if (!mounted) return;
      setState(() {
        _listings = list;
        _balanceMandal = bal;
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

  bool get _loggedIn => widget.user != null;

  @override
  Widget build(BuildContext context) {
    final name = widget.user?['username']?.toString();
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFF171A22), AppColors.bg],
          ),
        ),
        child: SafeArea(
          child: RefreshIndicator(
            color: AppColors.gold,
            onRefresh: _load,
            child: CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const BrandMark(compact: true),
                            const Spacer(),
                            if (_loggedIn)
                              BalanceChip(totalMandal: _balanceMandal),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Text(
                              name != null ? 'Merhaba, $name' : 'Ziyaretçi',
                              style: GoogleFonts.montserrat(
                                color: AppColors.muted,
                                fontSize: 13,
                              ),
                            ),
                            const Spacer(),
                            if (_loggedIn)
                              TextButton(
                                onPressed: () async {
                                  await api.setToken(null);
                                  if (!context.mounted) return;
                                  Navigator.of(context).pushAndRemoveUntil(
                                    MaterialPageRoute(
                                      builder: (_) =>
                                          const HomeScreen(user: null),
                                    ),
                                    (_) => false,
                                  );
                                },
                                child: Text(
                                  'Çıkış',
                                  style: GoogleFonts.montserrat(
                                    color: AppColors.gold,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              )
                            else
                              TextButton(
                                onPressed: () {
                                  Navigator.of(context).push(
                                    MaterialPageRoute(
                                      builder: (_) => const LoginScreen(),
                                    ),
                                  );
                                },
                                child: Text(
                                  'Giriş',
                                  style: GoogleFonts.montserrat(
                                    color: AppColors.gold,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                          ],
                        ),
                        const PlatformBanner(),
                        const SizedBox(height: 14),
                        const PillarsRow(),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _search,
                          onSubmitted: (_) => _load(),
                          decoration: InputDecoration(
                            hintText: 'Takas kaydı ara…',
                            suffixIcon: IconButton(
                              icon: const Icon(Icons.search, color: AppColors.gold),
                              onPressed: _load,
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 40,
                          child: ListView.separated(
                            scrollDirection: Axis.horizontal,
                            itemCount: categories.length,
                            separatorBuilder: (_, __) =>
                                const SizedBox(width: 8),
                            itemBuilder: (context, i) {
                              final c = categories[i];
                              final selected = (_category ?? 'Lobi') == c;
                              return ChoiceChip(
                                label: Text(c),
                                selected: selected,
                                onSelected: (_) {
                                  setState(() => _category = c);
                                  _load();
                                },
                                selectedColor: AppColors.gold,
                                labelStyle: GoogleFonts.montserrat(
                                  color: selected
                                      ? AppColors.bg
                                      : AppColors.ink,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 12,
                                ),
                                backgroundColor: AppColors.bgElevated,
                                side: BorderSide(
                                  color: selected
                                      ? AppColors.gold
                                      : AppColors.line,
                                ),
                                showCheckmark: false,
                              );
                            },
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'Takas kayıtları',
                          style: GoogleFonts.montserrat(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Change Score · doğrulanmış üyeler · güvenli takas',
                          style: GoogleFonts.montserrat(
                            color: AppColors.muted,
                            fontSize: 11,
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                    ),
                  ),
                ),
                if (_loading)
                  const SliverFillRemaining(
                    child: Center(
                      child: CircularProgressIndicator(color: AppColors.gold),
                    ),
                  )
                else if (_error != null)
                  SliverFillRemaining(
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(
                          _error!,
                          textAlign: TextAlign.center,
                          style: GoogleFonts.montserrat(color: AppColors.danger),
                        ),
                      ),
                    ),
                  )
                else if (_listings.isEmpty)
                  SliverFillRemaining(
                    child: Center(
                      child: Text(
                        'Henüz takas kaydı yok.\nİlk kaydı sen oluştur.',
                        textAlign: TextAlign.center,
                        style: GoogleFonts.montserrat(color: AppColors.muted),
                      ),
                    ),
                  )
                else
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(20, 0, 20, 100),
                    sliver: SliverList.separated(
                      itemCount: _listings.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 12),
                      itemBuilder: (context, index) {
                        final item =
                            Map<String, dynamic>.from(_listings[index] as Map);
                        return _ListingCard(
                          item: item,
                          onTap: () {
                            Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => ListingDetailScreen(
                                  listing: item,
                                  user: widget.user,
                                ),
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          if (!_loggedIn) {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const LoginScreen()),
            );
            return;
          }
          Navigator.of(context)
              .push(
            MaterialPageRoute(
              builder: (_) => CreateListingScreen(user: widget.user!),
            ),
          )
              .then((_) => _load());
        },
        backgroundColor: AppColors.gold,
        foregroundColor: AppColors.bg,
        icon: const Icon(Icons.swap_horiz),
        label: Text(
          'Takas kaydı',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w700),
        ),
      ),
      bottomNavigationBar: _loggedIn
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.gold,
                    side: const BorderSide(color: AppColors.gold),
                  ),
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => TradesScreen(user: widget.user!),
                      ),
                    );
                  },
                  icon: const Icon(Icons.account_tree_outlined),
                  label: const Text('Takaslarım / Zincir'),
                ),
              ),
            )
          : null,
    );
  }
}

class _ListingCard extends StatelessWidget {
  const _ListingCard({required this.item, required this.onTap});

  final Map<String, dynamic> item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final value = Map<String, dynamic>.from(item['value'] as Map? ?? {});
    final owner = Map<String, dynamic>.from(item['owner'] as Map? ?? {});
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.bgCard,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.line),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              item['title']?.toString() ?? '',
              style: GoogleFonts.montserrat(
                fontSize: 17,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${item['category']} · ${owner['username'] ?? '?'} · skor ${owner['change_score'] ?? '-'}',
              style: GoogleFonts.montserrat(
                color: AppColors.muted,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 12),
            ValueChip(value: value),
            if ((item['wanted_items']?.toString() ?? '').isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                'İstiyor: ${item['wanted_items']}',
                style: GoogleFonts.montserrat(
                  fontSize: 12,
                  color: AppColors.blue,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
