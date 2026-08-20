// ─── Güvenli JSON yardımcıları ────────────────────────────────────
int _asInt(dynamic v, [int fallback = 0]) {
  if (v == null) return fallback;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? fallback;
}

double? _asDoubleOrNull(dynamic v) {
  if (v == null || v == '') return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

String _asString(dynamic v, [String fallback = '']) {
  if (v == null) return fallback;
  return v.toString();
}

// ─── Kullanıcı ────────────────────────────────────────────────────
class User {
  final int id;
  final String username;
  final String role;
  final String country;
  final int score;
  final String? email;
  final String? phone;
  final String? city;

  const User({
    required this.id,
    required this.username,
    required this.role,
    required this.country,
    required this.score,
    this.email,
    this.phone,
    this.city,
  });

  factory User.fromJson(Map<String, dynamic> j) => User(
        id: _asInt(j['id']),
        username: _asString(j['username']),
        role: _asString(j['role'], 'user'),
        country: _asString(j['country'], 'tr'),
        score: _asInt(j['score']),
        email: j['email']?.toString(),
        phone: j['phone']?.toString(),
        city: j['city']?.toString(),
      );
}

// ─── İlan ────────────────────────────────────────────────────────
class Listing {
  final int id;
  final int no;
  final String title;
  final double? price;
  final String currency;
  final String status;
  final String category;
  final String city;
  final String country;
  final List<String> photos;
  final String? thumb;
  final String? description;
  final Map<String, dynamic>? attributes;
  final int viewCount;
  final bool isFavorite;
  final ListingOwner owner;
  final String? url;
  final double? createdAt;

  const Listing({
    required this.id,
    required this.no,
    required this.title,
    required this.currency,
    required this.status,
    required this.category,
    required this.city,
    required this.country,
    required this.photos,
    required this.owner,
    this.price,
    this.thumb,
    this.description,
    this.attributes,
    this.viewCount = 0,
    this.isFavorite = false,
    this.url,
    this.createdAt,
  });

  factory Listing.fromJson(Map<String, dynamic> j) => Listing(
        id: _asInt(j['id']),
        no: _asInt(j['no'], _asInt(j['id'])),
        title: _asString(j['title']),
        price: _asDoubleOrNull(j['price']),
        currency: _asString(j['currency'], 'TRY'),
        status: _asString(j['status'], 'active'),
        category: _asString(j['category']),
        city: _asString(j['city']),
        country: _asString(j['country'], 'tr'),
        photos: (j['photos'] as List?)?.map((e) => e.toString()).toList() ?? [],
        thumb: j['thumb']?.toString(),
        description: j['description']?.toString(),
        attributes: j['attributes'] is Map
            ? Map<String, dynamic>.from(j['attributes'] as Map)
            : null,
        viewCount: _asInt(j['view_count']),
        isFavorite: j['is_favorite'] == true,
        owner: ListingOwner.fromJson(
          j['owner'] is Map
              ? Map<String, dynamic>.from(j['owner'] as Map)
              : const {},
        ),
        url: j['url']?.toString(),
        createdAt: _asDoubleOrNull(j['created_at']),
      );

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
        'owner': {
          'id': owner.id,
          'username': owner.username,
          'phone': owner.phone,
          'city': owner.city,
        },
        'url': url,
        'created_at': createdAt,
      };

  String get priceFormatted {
    if (price == null) return 'Fiyat sorulur';
    final sym = currency == 'GBP' ? '£' : (currency == 'USD' ? '\$' : '₺');
    final val = price! % 1 == 0
        ? price!.toInt().toString()
        : price!.toStringAsFixed(0);
    return '$sym${_addThousands(val)}';
  }

  static String _addThousands(String s) {
    final buf = StringBuffer();
    for (var i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) buf.write('.');
      buf.write(s[i]);
    }
    return buf.toString();
  }
}

class ListingOwner {
  final int id;
  final String username;
  final String? phone;
  final String? city;

  const ListingOwner({
    required this.id,
    required this.username,
    this.phone,
    this.city,
  });

  factory ListingOwner.fromJson(Map<String, dynamic> j) => ListingOwner(
        id: _asInt(j['id']),
        username: _asString(j['username']),
        phone: j['phone']?.toString(),
        city: j['city']?.toString(),
      );
}

// ─── Konuşma & Mesaj ─────────────────────────────────────────────
class Conversation {
  final int id;
  final int? listingId;
  final String? listingTitle;
  final int unread;
  final double? updatedAt;

  const Conversation({
    required this.id,
    this.listingId,
    this.listingTitle,
    this.unread = 0,
    this.updatedAt,
  });

  factory Conversation.fromJson(Map<String, dynamic> j) => Conversation(
        id: _asInt(j['id']),
        listingId: j['listing_id'] == null ? null : _asInt(j['listing_id']),
        listingTitle: j['listing_title']?.toString(),
        unread: _asInt(j['unread']),
        updatedAt: _asDoubleOrNull(j['updated_at']),
      );
}

class Message {
  final int id;
  final int senderId;
  final String senderUsername;
  final String body;
  final double createdAt;
  final bool isMine;

  const Message({
    required this.id,
    required this.senderId,
    required this.senderUsername,
    required this.body,
    required this.createdAt,
    required this.isMine,
  });

  factory Message.fromJson(Map<String, dynamic> j) => Message(
        id: _asInt(j['id']),
        senderId: _asInt(j['sender_id']),
        senderUsername: _asString(j['sender_username']),
        body: _asString(j['body']),
        createdAt: _asDoubleOrNull(j['created_at']) ?? 0,
        isMine: j['is_mine'] == true,
      );
}

// ─── Bildirim ─────────────────────────────────────────────────────
class AppNotification {
  final int id;
  final String type;
  final String title;
  final String body;
  final String? link;
  final bool read;

  const AppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    this.link,
    this.read = false,
  });

  factory AppNotification.fromJson(Map<String, dynamic> j) => AppNotification(
        id: _asInt(j['id']),
        type: _asString(j['type'], 'info'),
        title: _asString(j['title']),
        body: _asString(j['body']),
        link: j['link']?.toString(),
        read: j['read'] == true,
      );
}
