import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/client.dart';
import '../auth/auth_intent.dart';
import '../theme/app_theme.dart';
import '../utils/listing_status_ux.dart';
import '../widgets/listing_presentation_layout.dart';
import '../widgets/listing_media.dart';
import 'create_listing_screen.dart';
import 'edit_listing_screen.dart';
import 'chat_detail_screen.dart';
import 'my_listings_screen.dart';

class ListingDetailScreen extends StatefulWidget {
  const ListingDetailScreen({
    super.key,
    required this.listing,
    required this.user,
    this.autoStartMessage = false,
  });

  final Map<String, dynamic> listing;
  final Map<String, dynamic>? user;
  final bool autoStartMessage;

  @override
  State<ListingDetailScreen> createState() => _ListingDetailScreenState();
}

class _ListingDetailScreenState extends State<ListingDetailScreen> {
  bool _busy = false;
  String? _result;
  bool _loadingMine = false;
  List<Map<String, dynamic>> _approvedMine = [];
  int? _selectedOfferId;
  bool _chainEngineEnabled = false;

  @override
  void initState() {
    super.initState();
    _loadChainStatus();
    if (widget.user != null) {
      _loadApprovedMine();
      if (widget.autoStartMessage) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _startMessage();
        });
      }
    }
  }

  Future<void> _startMessage() async {
    if (_isOwner) return;
    if (widget.user == null) {
      await openLoginGate(
        context,
        intent: AuthIntent.message.withListing(_asInt(widget.listing['id'])),
      );
      return;
    }
    setState(() => _busy = true);
    try {
      final conv = await api.startConversation(_asInt(widget.listing['id']));
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => ChatDetailScreen(
            user: widget.user!,
            conversation: conv,
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _offer() async {
    if (!_tradeOpen) {
      setState(() => _result = 'Bu ilan takasa kapalı veya takas edilmiştir.');
      return;
    }
    if (widget.user == null) {
      await openLoginGate(
        context,
        intent: AuthIntent.trade.withListing(_asInt(widget.listing['id'])),
      );
      return;
    }
    if (_selectedOfferId == null) {
      setState(() => _result =
          'Teklif için onaylı bir ilanınız yok. Önce fotoğraflı ilan oluşturup onaylatın.');
      return;
    }
    setState(() {
      _busy = true;
      _result = null;
    });
    try {
      final requestedId = _asInt(widget.listing['id']);
      final offeredId = _selectedOfferId!;
      final res = await api.createOffer({
        'requested_listing_ids': [requestedId],
        'offered_listing_ids': [offeredId],
        'idempotency_key':
            'offer-$requestedId-$offeredId-${DateTime.now().millisecondsSinceEpoch}',
      });
      final gap = res['value_gap'] as Map<String, dynamic>?;
      final exact = res['exact_match'] == true;
      setState(() {
        if (exact) {
          _result = 'Tam eşleşme! Durum: ${res['status'] ?? res['state']}';
        } else if (gap != null) {
          _result =
              '${res['value_gap_display'] ?? gap['display']}\n'
              'Fark gerçek para ile kapatılamaz. Başka onaylı ilan seçin veya yeni ilan ekleyin.';
        } else {
          _result = 'Teklif gönderildi · ${res['status'] ?? res['state']}';
        }
      });
    } on ApiException catch (e) {
      var msg = e.message;
      if (msg.contains('onaylı değil') || msg.contains('LISTING_NOT_APPROVED')) {
        msg =
            'Yalnızca onaylı ilanlarla teklif verilebilir. Seçtiğiniz ilan henüz onaylanmamış olabilir.';
      }
      setState(() => _result = msg);
    } catch (_) {
      setState(() => _result = 'Teklif gönderilemedi');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadChainStatus() async {
    try {
      final status = await api.changeChainStatus();
      if (!mounted) return;
      setState(() {
        _chainEngineEnabled = status['enabled'] == true;
      });
    } catch (_) {
      // Default remains false — production flag off / settlement NOT_IMPLEMENTED.
    }
  }

  bool get _tradeOpen {
    final ribbon = resolveListingRibbon(widget.listing);
    return ribbon == ListingTradeRibbon.none;
  }

  bool get _isOwner {
    final owner = Map<String, dynamic>.from(widget.listing['owner'] as Map? ?? {});
    final uid = widget.user?['id'];
    final oid = widget.listing['owner_id'] ?? owner['id'];
    if (uid == null || oid == null) {
      return widget.user != null &&
          owner['username'] == widget.user!['username'];
    }
    return uid == oid || uid.toString() == oid.toString();
  }

  bool get _isStaff {
    final role = widget.user?['role']?.toString();
    return role == 'admin' || role == 'superadmin' || role == 'moderator';
  }

  bool get _canForceDelete {
    final role = widget.user?['role']?.toString();
    return role == 'admin' || role == 'superadmin';
  }

  Future<void> _deleteListing() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(
          'İlanı sil',
          style: GoogleFonts.montserrat(fontWeight: FontWeight.w800),
        ),
        content: Text(
          _isOwner
              ? 'İlanınız yayından kaldırılacak. Devam edilsin mi?'
              : 'Bu ilanı (yönetici) soft-delete ile yayından kaldıracaksınız.',
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
    setState(() => _busy = true);
    try {
      await api.cancelListing(_asInt(widget.listing['id']));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('İlan silindi')),
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Silinemedi')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadApprovedMine() async {
    setState(() => _loadingMine = true);
    try {
      final raw = await api.myListings();
      final targetId = widget.listing['id'];
      final approved = <Map<String, dynamic>>[];
      for (final item in raw) {
        final m = Map<String, dynamic>.from(item as Map);
        final status = (m['status']?.toString() ?? '').toUpperCase();
        if (status != 'APPROVED' && status != 'ACTIVE') continue;
        if (m['id'] == targetId) continue;
        approved.add(m);
      }
      if (!mounted) return;
      setState(() {
        _approvedMine = approved;
        _selectedOfferId = approved.isEmpty ? null : approved.first['id'] as int?;
        if (_selectedOfferId == null && approved.isNotEmpty) {
          final v = approved.first['id'];
          _selectedOfferId = v is int ? v : (v as num).toInt();
        }
        _loadingMine = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _approvedMine = [];
        _loadingMine = false;
      });
    }
  }

  int _asInt(dynamic v) {
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.parse(v.toString());
  }

  @override
  Widget build(BuildContext context) {
    final owner = Map<String, dynamic>.from(widget.listing['owner'] as Map? ?? {});
    final ribbon = resolveListingRibbon(widget.listing);

    return Scaffold(
      backgroundColor: const Color(0xFF050607),
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: const Color(0xFF050607),
            title: Text(
              'CHANGE X',
              style: GoogleFonts.montserrat(fontWeight: FontWeight.w800),
            ),
          ),
          SliverToBoxAdapter(
            child: ListingDetailLayout(
              listing: widget.listing,
              includeGallery: true,
              actions: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '${owner['username'] ?? '?'} · skor ${owner['change_score'] ?? '-'}',
                    style: GoogleFonts.montserrat(color: AppColors.muted, fontSize: 12),
                  ),
                  if (!_isOwner) ...[
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.gold,
                        side: const BorderSide(color: AppColors.gold),
                        minimumSize: const Size(48, 48),
                      ),
                      onPressed: _busy ? null : _startMessage,
                      icon: const Icon(Icons.chat_bubble_outline),
                      label: const Text('Satıcıya Mesaj Gönder'),
                    ),
                  ],
                  ChainEngineNotice(chainEngineEnabled: _chainEngineEnabled),
                  if (_isOwner || _isStaff) ...[
                    const SizedBox(height: 14),
                    _OwnerModerationPanel(listing: widget.listing),
                  ],
                  if (_isOwner &&
                      listingUxEditable(resolveListingUxState(widget.listing))) ...[
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      onPressed: () async {
                        final ok = await Navigator.of(context).push<bool>(
                          MaterialPageRoute(
                            builder: (_) => EditListingScreen(
                              user: widget.user!,
                              listing: widget.listing,
                            ),
                          ),
                        );
                        if (ok == true && context.mounted) {
                          try {
                            final fresh = await api.getListing(_asInt(widget.listing['id']));
                            if (!context.mounted) return;
                            Navigator.of(context).pushReplacement(
                              MaterialPageRoute(
                                builder: (_) => ListingDetailScreen(
                                  listing: fresh,
                                  user: widget.user,
                                ),
                              ),
                            );
                          } catch (_) {}
                        }
                      },
                      icon: const Icon(Icons.edit_outlined),
                      label: const Text('Düzenle / Fotoğraf ekle'),
                    ),
                  ],
                  if ((_isOwner || _canForceDelete) &&
                      listingUxDeletable(resolveListingUxState(widget.listing))) ...[
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.danger,
                        side: const BorderSide(color: AppColors.danger),
                        minimumSize: const Size(48, 48),
                      ),
                      onPressed: _busy ? null : _deleteListing,
                      icon: const Icon(Icons.delete_outline),
                      label: Text(
                        _isOwner ? 'İlanımı sil' : 'İlanı sil (yönetici)',
                      ),
                    ),
                  ],
                  const SizedBox(height: 18),
                  if (_isOwner && !_tradeOpen) ...[
                    Text(
                      resolveListingUxState(widget.listing) == ListingUxState.pending
                          ? 'İlanınız incelemede. Onaylanınca ana sayfada ve tekliflerde görünür.'
                          : listingUxBody(widget.listing),
                      style: GoogleFonts.montserrat(color: AppColors.muted, height: 1.35),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => MyListingsScreen(user: widget.user!),
                          ),
                        );
                      },
                      icon: const Icon(Icons.photo_library_outlined),
                      label: const Text('İlanlarıma dön'),
                    ),
                  ] else ...[
                    Text(
                      'Takas teklifi ver',
                      style: GoogleFonts.montserrat(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 8),
                    if (!_tradeOpen)
                      Text(
                        ribbon == ListingTradeRibbon.exchanged
                            ? 'Bu ürün takas edilmiştir. Yeni teklif alınamaz.'
                            : ribbon == ListingTradeRibbon.rejected
                                ? 'Bu ilan reddedildi — teklif alınamaz.'
                                : ribbon == ListingTradeRibbon.inReview
                                    ? 'İlan incelemede — teklif için onay bekleniyor.'
                                    : 'Bu ilan takasa kapalıdır.',
                        style: GoogleFonts.montserrat(color: AppColors.danger),
                      )
                    else if (widget.user == null)
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            'Takas yapmak için hesabınıza giriş yapmanız gerekiyor.',
                            style: GoogleFonts.montserrat(color: AppColors.muted, height: 1.35),
                          ),
                          const SizedBox(height: 12),
                          SizedBox(
                            height: 52,
                            child: FilledButton(
                              onPressed: () {
                                openLoginGate(
                                  context,
                                  intent: AuthIntent.trade.withListing(
                                    _asInt(widget.listing['id']),
                                  ),
                                );
                              },
                              child: const Text('Takas Yap'),
                            ),
                          ),
                        ],
                      )
                    else if (_loadingMine)
                      const Center(child: CircularProgressIndicator())
                    else if (_approvedMine.isEmpty) ...[
                      Text(
                        'Onaylı ilanınız yok. Teklif için önce fotoğraflı ilan oluşturun.',
                        style: GoogleFonts.montserrat(color: AppColors.muted, height: 1.35),
                      ),
                      const SizedBox(height: 12),
                      FilledButton.icon(
                        onPressed: () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => CreateListingScreen(user: widget.user!),
                            ),
                          );
                          _loadApprovedMine();
                        },
                        icon: const Icon(Icons.add_a_photo_outlined),
                        label: const Text('Fotoğraflı ilan oluştur'),
                      ),
                    ] else ...[
                      DropdownButtonFormField<int>(
                        value: _selectedOfferId,
                        decoration: const InputDecoration(
                          labelText: 'Teklif edeceğin onaylı ilan',
                        ),
                        items: [
                          for (final m in _approvedMine)
                            DropdownMenuItem(
                              value: _asInt(m['id']),
                              child: Text('${m['title']} · #${m['id']}', overflow: TextOverflow.ellipsis),
                            ),
                        ],
                        onChanged: _busy ? null : (v) => setState(() => _selectedOfferId = v),
                      ),
                      const SizedBox(height: 8),
                      SizedBox(
                        height: 52,
                        child: FilledButton(
                          onPressed: _busy ? null : _offer,
                          child: Text(_busy ? 'Gönderiliyor…' : 'Takas teklifi ver'),
                        ),
                      ),
                    ],
                  ],
                  if (_result != null) ...[
                    const SizedBox(height: 14),
                    Text(_result!, style: GoogleFonts.montserrat(height: 1.35)),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _OwnerModerationPanel extends StatelessWidget {
  const _OwnerModerationPanel({required this.listing});

  final Map<String, dynamic> listing;

  @override
  Widget build(BuildContext context) {
    final state = resolveListingUxState(listing);
    final color = listingUxChipColor(state);
    final reason = listing['moderation_reason']?.toString().trim() ?? '';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        border: Border.all(color: color.withValues(alpha: 0.45)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            listingUxChipLabel(state),
            style: GoogleFonts.montserrat(
              color: color,
              fontWeight: FontWeight.w800,
              fontSize: 13,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            listingUxBody(listing),
            style: GoogleFonts.montserrat(
              color: AppColors.ink,
              fontSize: 13,
              height: 1.35,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            listingImageStatusLine(listing),
            style: GoogleFonts.montserrat(
              color: AppColors.muted,
              fontSize: 11,
            ),
          ),
          if (reason.isNotEmpty &&
              (state == ListingUxState.rejected ||
                  state == ListingUxState.editRequired)) ...[
            const SizedBox(height: 8),
            Text(
              'Gerekçe: $reason',
              style: GoogleFonts.montserrat(
                color: AppColors.danger,
                fontSize: 12,
                height: 1.3,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
