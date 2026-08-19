import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:provider/provider.dart';
import '../../core/api_client.dart';
import '../../core/auth_provider.dart';
import '../../core/models.dart';
import '../listings/screens/listing_detail_screen.dart';

class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  List<Listing> _items = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final resp = await ApiClient.get('/listings/favorites', auth: true);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (resp.ok && resp.data != null) {
        final data = resp.data as Map<String, dynamic>;
        _items = (data['items'] as List)
            .map((e) => Listing.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    });
  }

  Future<void> _removeFav(int id) async {
    await ApiClient.delete('/listings/favorites',
        query: {'id': id.toString()}, auth: true);
    setState(() => _items.removeWhere((l) => l.id == id));
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    if (!auth.isLoggedIn) {
      return const Scaffold(
        body: Center(child: Text('Favorileri görmek için giriş yapın.')),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Favorilerim')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _items.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.favorite_border,
                          size: 64, color: Colors.grey),
                      SizedBox(height: 12),
                      Text('Henüz favori ilan yok.',
                          style: TextStyle(color: Colors.grey)),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.separated(
                    padding: const EdgeInsets.all(12),
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (_, i) => _FavCard(
                      listing: _items[i],
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) =>
                              ListingDetailScreen(id: _items[i].id),
                        ),
                      ).then((_) => _load()),
                      onRemove: () => _removeFav(_items[i].id),
                    ),
                  ),
                ),
    );
  }
}

class _FavCard extends StatelessWidget {
  final Listing listing;
  final VoidCallback onTap;
  final VoidCallback onRemove;

  const _FavCard({
    required this.listing,
    required this.onTap,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        onTap: onTap,
        leading: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: listing.thumb != null
              ? CachedNetworkImage(
                  imageUrl: listing.thumb!,
                  width: 60,
                  height: 60,
                  fit: BoxFit.cover,
                )
              : Container(
                  width: 60,
                  height: 60,
                  color: const Color(0xFFECEFF1),
                  child: const Icon(Icons.image_outlined, color: Colors.grey),
                ),
        ),
        title: Text(listing.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        subtitle: Text(
          listing.priceFormatted,
          style: const TextStyle(
              fontWeight: FontWeight.w800, color: Color(0xFF002F34)),
        ),
        trailing: IconButton(
          icon: const Icon(Icons.favorite, color: Colors.red),
          onPressed: onRemove,
        ),
      ),
    );
  }
}
