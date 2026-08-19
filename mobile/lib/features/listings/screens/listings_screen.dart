import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../../core/api_client.dart';
import '../../../core/models.dart';
import 'listing_detail_screen.dart';

class ListingsScreen extends StatefulWidget {
  const ListingsScreen({super.key});

  @override
  State<ListingsScreen> createState() => _ListingsScreenState();
}

class _ListingsScreenState extends State<ListingsScreen> {
  final _searchCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();

  List<Listing> _items = [];
  bool _loading = false;
  bool _hasMore = true;
  int _page = 1;
  String _sort = 'new';
  String _region = 'all';
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
    _scrollCtrl.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollCtrl.position.pixels >=
            _scrollCtrl.position.maxScrollExtent - 200 &&
        !_loading &&
        _hasMore) {
      _loadMore();
    }
  }

  Future<void> _load({bool reset = true}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      if (reset) {
        _items = [];
        _page = 1;
        _hasMore = true;
      }
    });

    final q = _searchCtrl.text.trim();
    final resp = await ApiClient.get('/listings', query: {
      if (q.isNotEmpty) 'q': q,
      'sort': _sort,
      'region': _region,
      'page': _page.toString(),
      'per_page': '20',
    });

    if (!mounted) return;
    setState(() {
      _loading = false;
      if (resp.ok && resp.data != null) {
        _error = null;
        final data = resp.data as Map<String, dynamic>;
        final newItems = (data['items'] as List)
            .map((e) => Listing.fromJson(e as Map<String, dynamic>))
            .toList();
        if (reset) {
          _items = newItems;
        } else {
          _items.addAll(newItems);
        }
        _hasMore = _page < (data['pages'] as int? ?? 1);
      } else {
        _error = resp.error ?? 'Ilanlar yuklenemedi.';
        if (reset) _items = [];
      }
    });
  }

  Future<void> _loadMore() async {
    _page++;
    await _load(reset: false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BenimBazar'),
        actions: [
          IconButton(
            icon: const Icon(Icons.filter_list),
            onPressed: _showFilter,
          ),
        ],
      ),
      body: Column(
        children: [
          // Arama çubuğu
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
            child: TextField(
              controller: _searchCtrl,
              decoration: InputDecoration(
                hintText: 'İlan ara…',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchCtrl.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchCtrl.clear();
                          _load();
                        },
                      )
                    : null,
              ),
              onSubmitted: (_) => _load(),
              textInputAction: TextInputAction.search,
            ),
          ),

          // Bölge chip'leri
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Row(
              children: [
                for (final r in [
                  ('all', 'Tümü'),
                  ('tr', '🇹🇷 Türkiye'),
                  ('kktc', '🇨🇾 KKTC'),
                ])
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(r.$2),
                      selected: _region == r.$1,
                      onSelected: (_) {
                        setState(() => _region = r.$1);
                        _load();
                      },
                    ),
                  ),
              ],
            ),
          ),

          // Liste
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => _load(),
              child: _loading && _items.isEmpty
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null && _items.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 80),
                            Icon(Icons.cloud_off_outlined,
                                size: 56, color: Colors.grey.shade500),
                            const SizedBox(height: 12),
                            Padding(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 24),
                              child: Text(
                                _error!,
                                textAlign: TextAlign.center,
                                style: TextStyle(color: Colors.grey.shade700),
                              ),
                            ),
                            const SizedBox(height: 16),
                            Center(
                              child: FilledButton.icon(
                                onPressed: _load,
                                icon: const Icon(Icons.refresh),
                                label: const Text('Tekrar dene'),
                              ),
                            ),
                          ],
                        )
                  : _items.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: const [
                            SizedBox(height: 80),
                            Center(child: Text('Ilan bulunamadi.')),
                          ],
                        )
                      : GridView.builder(
                      controller: _scrollCtrl,
                      padding: const EdgeInsets.all(10),
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 2,
                        childAspectRatio: 0.72,
                        crossAxisSpacing: 10,
                        mainAxisSpacing: 10,
                      ),
                      itemCount: _items.length + (_hasMore ? 1 : 0),
                      itemBuilder: (ctx, i) {
                        if (i >= _items.length) {
                          return const Center(
                              child: CircularProgressIndicator());
                        }
                        return _ListingCard(
                          listing: _items[i],
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => ListingDetailScreen(
                                  id: _items[i].id),
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }

  void _showFilter() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Sıralama',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 12),
            for (final s in [
              ('new', 'En Yeni'),
              ('price_asc', 'En Ucuz'),
              ('price_desc', 'En Pahalı'),
              ('popular', 'En Popüler'),
            ])
              RadioListTile<String>(
                title: Text(s.$2),
                value: s.$1,
                groupValue: _sort,
                onChanged: (v) {
                  setState(() => _sort = v!);
                  Navigator.pop(context);
                  _load();
                },
              ),
          ],
        ),
      ),
    );
  }
}

class _ListingCard extends StatelessWidget {
  final Listing listing;
  final VoidCallback onTap;

  const _ListingCard({required this.listing, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Fotoğraf
            Expanded(
              child: listing.thumb != null
                  ? CachedNetworkImage(
                      imageUrl: listing.thumb!,
                      fit: BoxFit.cover,
                      width: double.infinity,
                      placeholder: (_, __) => Container(
                        color: const Color(0xFFECEFF1),
                        child: const Center(child: CircularProgressIndicator()),
                      ),
                      errorWidget: (_, __, ___) => Container(
                        color: const Color(0xFFECEFF1),
                        child: const Icon(Icons.image_not_supported_outlined,
                            size: 40, color: Colors.grey),
                      ),
                    )
                  : Container(
                      color: const Color(0xFFECEFF1),
                      child: const Center(
                        child: Icon(Icons.sell_outlined,
                            size: 48, color: Colors.grey),
                      ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    listing.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    listing.priceFormatted,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF002F34),
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      const Icon(Icons.location_on_outlined,
                          size: 12, color: Colors.grey),
                      const SizedBox(width: 2),
                      Expanded(
                        child: Text(
                          listing.city,
                          style: const TextStyle(
                              fontSize: 11, color: Colors.grey),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
