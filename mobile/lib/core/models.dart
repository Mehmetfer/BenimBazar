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
        id: j['id'] as int,
        username: j['username'] as String,
        role: j['role'] as String? ?? 'user',
        country: j['country'] as String? ?? 'tr',
        score: j['score'] as int? ?? 0,
        email: j['email'] as String?,
        phone: j['phone'] as String?,
        city: j['city'] as String?,
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
        id: j['id'] as int,
        no: j['no'] as int? ?? j['id'] as int,
        title: j['title'] as String? ?? '',
        price: j['price'] != null ? (j['price'] as num).toDouble() : null,
        currency: j['currency'] as String? ?? 'TRY',
        status: j['status'] as String? ?? 'active',
        category: j['category'] as String? ?? '',
        city: j['city'] as String? ?? '',
        country: j['country'] as String? ?? 'tr',
        photos: (j['photos'] as List?)?.map((e) => e.toString()).toList() ?? [],
        thumb: j['thumb'] as String?,
        description: j['description'] as String?,
        attributes: j['attributes'] as Map<String, dynamic>?,
        viewCount: j['view_count'] as int? ?? 0,
        isFavorite: j['is_favorite'] as bool? ?? false,
        owner: ListingOwner.fromJson(
          j['owner'] as Map<String, dynamic>? ?? {},
        ),
        url: j['url'] as String?,
        createdAt: j['created_at'] != null
            ? (j['created_at'] as num).toDouble()
            : null,
      );

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
        id: j['id'] as int? ?? 0,
        username: j['username'] as String? ?? '',
        phone: j['phone'] as String?,
        city: j['city'] as String?,
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
        id: j['id'] as int,
        listingId: j['listing_id'] as int?,
        listingTitle: j['listing_title'] as String?,
        unread: j['unread'] as int? ?? 0,
        updatedAt: j['updated_at'] != null
            ? (j['updated_at'] as num).toDouble()
            : null,
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
        id: j['id'] as int,
        senderId: j['sender_id'] as int,
        senderUsername: j['sender_username'] as String? ?? '',
        body: j['body'] as String? ?? '',
        createdAt: (j['created_at'] as num).toDouble(),
        isMine: j['is_mine'] as bool? ?? false,
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
        id: j['id'] as int,
        type: j['type'] as String? ?? 'info',
        title: j['title'] as String? ?? '',
        body: j['body'] as String? ?? '',
        link: j['link'] as String?,
        read: j['read'] as bool? ?? false,
      );
}
