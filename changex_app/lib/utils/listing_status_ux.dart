import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// User-facing listing lifecycle for My Listings / owner detail.
enum ListingUxState {
  draft,
  pending,
  approved,
  rejected,
  editRequired,
  suspended,
  reserved,
  traded,
  deleted,
  expired,
  unknown,
}

ListingUxState resolveListingUxState(Map<String, dynamic> listing) {
  final status = (listing['status']?.toString() ?? '').toUpperCase();
  switch (status) {
    case 'DRAFT':
      return ListingUxState.draft;
    case 'PENDING_MODERATION':
    case 'AI_REVIEW':
    case 'ADMIN_REVIEW':
    case 'MODERATION_UNAVAILABLE':
    case 'ESCALATED':
      return ListingUxState.pending;
    case 'APPROVED':
    case 'ACTIVE':
      return ListingUxState.approved;
    case 'REJECTED':
      return ListingUxState.rejected;
    case 'EDIT_REQUIRED':
      return ListingUxState.editRequired;
    case 'SUSPENDED':
      return ListingUxState.suspended;
    case 'RESERVED':
      return ListingUxState.reserved;
    case 'TRADED':
      return ListingUxState.traded;
    case 'CANCELLED':
      return ListingUxState.deleted;
    case 'EXPIRED':
      return ListingUxState.expired;
    default:
      return ListingUxState.unknown;
  }
}

/// Short chip label (never raw English enums for end users).
String listingUxChipLabel(ListingUxState state) {
  switch (state) {
    case ListingUxState.draft:
      return 'Taslak';
    case ListingUxState.pending:
      return 'İncelemede';
    case ListingUxState.approved:
      return 'Yayında';
    case ListingUxState.rejected:
      return 'Reddedildi';
    case ListingUxState.editRequired:
      return 'Düzenleme gerekli';
    case ListingUxState.suspended:
      return 'Askıda';
    case ListingUxState.reserved:
      return 'Rezerve';
    case ListingUxState.traded:
      return 'Takas edildi';
    case ListingUxState.deleted:
      return 'Silindi';
    case ListingUxState.expired:
      return 'Süresi doldu';
    case ListingUxState.unknown:
      return 'Durum güncellendi';
  }
}

/// Longer reassurance copy — prevents “ilanım kayboldu” feeling.
String listingUxBody(Map<String, dynamic> listing) {
  final msg = listing['user_message']?.toString().trim();
  if (msg != null && msg.isNotEmpty) return msg;
  switch (resolveListingUxState(listing)) {
    case ListingUxState.draft:
      return 'Taslak kaydedildi. Yayınlamak için tamamlayıp gönderin.';
    case ListingUxState.pending:
      return 'İlanınız incelemede. Ana sayfada görünmez; İlanlarım’da duruyor.';
    case ListingUxState.approved:
      return 'İlanınız yayında — ana sayfada görünür.';
    case ListingUxState.rejected:
      return 'İlanınız kurallara uygun bulunmadı. Gerekirse düzenleyip yeniden gönderin.';
    case ListingUxState.editRequired:
      return 'Düzenleme isteniyor. Fotoğraf veya metni güncelleyip kaydedin.';
    case ListingUxState.suspended:
      return 'İlanınız askıya alındı.';
    case ListingUxState.reserved:
      return 'Takas rezervinde — yeni teklif alınamaz.';
    case ListingUxState.traded:
      return 'Takas tamamlandı.';
    case ListingUxState.deleted:
      return 'İlan silindi / yayından kaldırıldı. Kayıt İlanlarım’da arşivde kalır.';
    case ListingUxState.expired:
      return 'İlan süresi doldu.';
    case ListingUxState.unknown:
      return 'Durum güncellendi.';
  }
}

Color listingUxChipColor(ListingUxState state) {
  switch (state) {
    case ListingUxState.pending:
    case ListingUxState.editRequired:
      return AppColors.blue;
    case ListingUxState.approved:
      return AppColors.gold;
    case ListingUxState.rejected:
    case ListingUxState.suspended:
    case ListingUxState.deleted:
      return AppColors.danger;
    case ListingUxState.traded:
    case ListingUxState.reserved:
      return AppColors.muted;
    case ListingUxState.draft:
    case ListingUxState.expired:
    case ListingUxState.unknown:
      return AppColors.muted;
  }
}

bool listingUxEditable(ListingUxState state) {
  switch (state) {
    case ListingUxState.traded:
    case ListingUxState.deleted:
    case ListingUxState.reserved:
    case ListingUxState.expired:
      return false;
    default:
      return true;
  }
}

/// Owner (or staff via cancel API) may soft-delete unless already closed/traded.
bool listingUxDeletable(ListingUxState state) {
  switch (state) {
    case ListingUxState.traded:
    case ListingUxState.deleted:
    case ListingUxState.reserved:
      return false;
    default:
      return true;
  }
}

/// Filter buckets for My Listings tabs.
enum MyListingsFilter { all, pending, live, closed }

bool listingMatchesFilter(Map<String, dynamic> listing, MyListingsFilter filter) {
  final state = resolveListingUxState(listing);
  switch (filter) {
    case MyListingsFilter.all:
      return true;
    case MyListingsFilter.pending:
      return state == ListingUxState.pending ||
          state == ListingUxState.editRequired ||
          state == ListingUxState.draft;
    case MyListingsFilter.live:
      return state == ListingUxState.approved || state == ListingUxState.reserved;
    case MyListingsFilter.closed:
      return state == ListingUxState.rejected ||
          state == ListingUxState.deleted ||
          state == ListingUxState.traded ||
          state == ListingUxState.suspended ||
          state == ListingUxState.expired;
  }
}

String myListingsFilterLabel(MyListingsFilter filter) {
  switch (filter) {
    case MyListingsFilter.all:
      return 'Tümü';
    case MyListingsFilter.pending:
      return 'İncelemede';
    case MyListingsFilter.live:
      return 'Yayında';
    case MyListingsFilter.closed:
      return 'Kapalı';
  }
}

/// Aggregate image status line for owner (from photos[] or photo count).
String listingImageStatusLine(Map<String, dynamic> listing) {
  final photos = listing['photos'];
  if (photos is List && photos.isNotEmpty) {
    var pending = 0;
    var approved = 0;
    var flagged = 0;
    for (final raw in photos) {
      if (raw is! Map) continue;
      final s = (raw['moderation_status']?.toString() ?? '').toUpperCase();
      if (s == 'APPROVED' || s == 'AI_SAFE') {
        approved++;
      } else if (s == 'FLAGGED' || s == 'REJECTED') {
        flagged++;
      } else {
        pending++;
      }
    }
    final parts = <String>[];
    if (approved > 0) parts.add('$approved onaylı');
    if (pending > 0) parts.add('$pending incelemede');
    if (flagged > 0) parts.add('$flagged işaretli');
    if (parts.isEmpty) return '${photos.length} fotoğraf';
    return '${photos.length} fotoğraf · ${parts.join(' · ')}';
  }
  final urls = listing['all_photo_urls'] ?? listing['photo_urls'];
  final n = urls is List ? urls.length : 0;
  final state = resolveListingUxState(listing);
  if (state == ListingUxState.pending) {
    return '$n fotoğraf · moderasyon bekliyor';
  }
  return '$n fotoğraf';
}
