import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/api_client.dart';
import '../../../core/auth_provider.dart';
import '../../../core/models.dart';
import '../../messages/messages_screen.dart';

class ListingDetailScreen extends StatefulWidget {
  final int id;

  const ListingDetailScreen({super.key, required this.id});

  @override
  State<ListingDetailScreen> createState() => _ListingDetailScreenState();
}

class _ListingDetailScreenState extends State<ListingDetailScreen> {
  Listing? _listing;
  bool _loading = true;
  bool _favLoading = false;
  int _photoIndex = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final resp = await ApiClient.get(
      '/listings/detail',
      query: {'id': widget.id.toString()},
      auth: true,
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (resp.ok && resp.data != null) {
        _listing = Listing.fromJson(resp.data as Map<String, dynamic>);
      }
    });
  }

  Future<void> _toggleFav() async {
    if (_listing == null) return;
    final auth = context.read<AuthProvider>();
    if (!auth.isLoggedIn) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Favoriye eklemek için giriş yapın.')),
      );
      return;
    }
    setState(() => _favLoading = true);
    final isFav = _listing!.isFavorite;
    ApiResponse resp;
    if (isFav) {
      resp = await ApiClient.delete(
        '/listings/favorites',
        query: {'id': widget.id.toString()},
        auth: true,
      );
    } else {
      resp = await ApiClient.post(
        '/listings/favorites',
        {'id': widget.id},
        auth: true,
      );
    }
    if (!mounted) return;
    setState(() {
      _favLoading = false;
      if (resp.ok) {
        _listing = Listing.fromJson({
          ..._listing!.toMap(),
          'is_favorite': !isFav,
        });
      }
    });
  }

  Future<void> _callPhone() async {
    final phone = _listing?.owner.phone;
    if (phone == null) return;
    final uri = Uri.parse('tel:$phone');
    if (await canLaunchUrl(uri)) await launchUrl(uri);
  }

  Future<void> _sendMessage() async {
    final auth = context.read<AuthProvider>();
    if (!auth.isLoggedIn) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Mesaj göndermek için giriş yapın.')),
      );
      return;
    }
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => MessagesScreen(
          listingId: widget.id,
          listingTitle: _listing?.title,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_listing == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('İlan bulunamadı.')),
      );
    }
    final l = _listing!;

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          // Fotoğraf galerisi
          SliverAppBar(
            expandedHeight: 280,
            pinned: true,
            actions: [
              _favLoading
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              color: Colors.white, strokeWidth: 2)),
                    )
                  : IconButton(
                      icon: Icon(
                        l.isFavorite ? Icons.favorite : Icons.favorite_border,
                        color: l.isFavorite ? Colors.red : Colors.white,
                      ),
                      onPressed: _toggleFav,
                    ),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: l.photos.isNotEmpty
                  ? GestureDetector(
                      onTap: () => _openGallery(context),
                      child: Stack(
                        children: [
                          PageView.builder(
                            itemCount: l.photos.length,
                            onPageChanged: (i) =>
                                setState(() => _photoIndex = i),
                            itemBuilder: (_, i) => CachedNetworkImage(
                              imageUrl: l.photos[i],
                              fit: BoxFit.cover,
                            ),
                          ),
                          if (l.photos.length > 1)
                            Positioned(
                              bottom: 10,
                              right: 12,
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.black54,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(
                                  '${_photoIndex + 1}/${l.photos.length}',
                                  style: const TextStyle(
                                      color: Colors.white, fontSize: 12),
                                ),
                              ),
                            ),
                        ],
                      ),
                    )
                  : Container(
                      color: const Color(0xFFECEFF1),
                      child: const Center(
                        child: Icon(Icons.sell_outlined,
                            size: 80, color: Colors.grey),
                      ),
                    ),
            ),
          ),

          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Başlık & Fiyat
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          l.title,
                          style: const TextStyle(
                              fontSize: 20, fontWeight: FontWeight.w800),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        l.priceFormatted,
                        style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w900,
                          color: Color(0xFF002F34),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),

                  // İlan no & Konum
                  Row(
                    children: [
                      const Icon(Icons.location_on_outlined,
                          size: 14, color: Colors.grey),
                      const SizedBox(width: 4),
                      Text(l.city,
                          style: const TextStyle(color: Colors.grey)),
                      const Spacer(),
                      Text(
                        '#${l.no}',
                        style: const TextStyle(
                            color: Colors.grey,
                            fontSize: 12,
                            fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Divider(),

                  // Açıklama
                  if (l.description != null && l.description!.isNotEmpty) ...[
                    const Text('Açıklama',
                        style: TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 16)),
                    const SizedBox(height: 8),
                    Text(l.description!, style: const TextStyle(height: 1.5)),
                    const SizedBox(height: 16),
                    const Divider(),
                  ],

                  // Satıcı bilgisi
                  const Text('Satıcı',
                      style: TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 16)),
                  const SizedBox(height: 8),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: CircleAvatar(
                      backgroundColor: const Color(0xFF002F34),
                      child: Text(
                        l.owner.username.substring(0, 1).toUpperCase(),
                        style: const TextStyle(color: Colors.white),
                      ),
                    ),
                    title: Text(l.owner.username,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle:
                        l.owner.city != null ? Text(l.owner.city!) : null,
                  ),
                  const SizedBox(height: 80), // bottom bar için boşluk
                ],
              ),
            ),
          ),
        ],
      ),

      // Alt aksiyonlar
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Row(
            children: [
              if (l.owner.phone != null)
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.phone_outlined),
                    label: const Text('Ara'),
                    onPressed: _callPhone,
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(0, 50),
                      side: const BorderSide(color: Color(0xFF002F34)),
                      foregroundColor: const Color(0xFF002F34),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                ),
              if (l.owner.phone != null) const SizedBox(width: 10),
              Expanded(
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.message_outlined),
                  label: const Text('Mesaj Gönder'),
                  onPressed: _sendMessage,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openGallery(BuildContext context) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => _GalleryView(
          photos: _listing!.photos,
          initialIndex: _photoIndex,
        ),
      ),
    );
  }
}

// Listing.toMap() için extension
extension _ListingMap on Listing {
  Map<String, dynamic> toMap() => {
        'id': id,
        'no': no,
        'title': title,
        'price': price,
        'currency': currency,
        'status': status,
        'category': category,
        'city': city,
        'country': country,
        'photos': photos,
        'thumb': thumb,
        'description': description,
        'attributes': attributes,
        'view_count': viewCount,
        'is_favorite': isFavorite,
        'owner': {'id': owner.id, 'username': owner.username, 'phone': owner.phone, 'city': owner.city},
        'url': url,
        'created_at': createdAt,
      };
}

class _GalleryView extends StatelessWidget {
  final List<String> photos;
  final int initialIndex;

  const _GalleryView({required this.photos, required this.initialIndex});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: PhotoViewGallery.builder(
        itemCount: photos.length,
        pageController: PageController(initialPage: initialIndex),
        builder: (_, i) => PhotoViewGalleryPageOptions(
          imageProvider: CachedNetworkImageProvider(photos[i]),
          minScale: PhotoViewComputedScale.contained,
          maxScale: PhotoViewComputedScale.covered * 2,
        ),
        backgroundDecoration: const BoxDecoration(color: Colors.black),
      ),
    );
  }
}
