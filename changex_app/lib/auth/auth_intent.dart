import 'package:flutter/material.dart';

import '../api/client.dart';
import '../screens/admin_panel_screen.dart';
import '../screens/create_listing_screen.dart';
import '../screens/home_screen.dart';
import '../screens/listing_detail_screen.dart';
import '../screens/login_screen.dart';
import '../screens/messages_inbox_screen.dart';
import '../screens/trades_screen.dart';

/// Why the guest was sent to login, and where to continue after success.
enum AuthAction {
  browse,
  trade,
  message,
  createListing,
  messages,
  trades,
  profile,
}

class AuthIntent {
  const AuthIntent({
    required this.reason,
    this.action = AuthAction.browse,
    this.listingId,
  });

  final String reason;
  final AuthAction action;
  final int? listingId;

  static const trade = AuthIntent(
    reason: 'Takas yapmak için hesabınıza giriş yapmanız gerekiyor.',
    action: AuthAction.trade,
  );

  static const message = AuthIntent(
    reason: 'Satıcıya mesaj göndermek için hesabınıza giriş yapmanız gerekiyor.',
    action: AuthAction.message,
  );

  static const createListing = AuthIntent(
    reason: 'İlan vermek için hesabınıza giriş yapmanız gerekiyor.',
    action: AuthAction.createListing,
  );

  static const messagesInbox = AuthIntent(
    reason: 'Mesaj kutusunu görmek için hesabınıza giriş yapmanız gerekiyor.',
    action: AuthAction.messages,
  );

  static const trades = AuthIntent(
    reason: 'Takaslarınızı yönetmek için hesabınıza giriş yapmanız gerekiyor.',
    action: AuthAction.trades,
  );

  static const profile = AuthIntent(
    reason: 'Profil işlemleri için hesabınıza giriş yapmanız gerekiyor.',
    action: AuthAction.profile,
  );

  AuthIntent withListing(int id) => AuthIntent(
        reason: reason,
        action: action,
        listingId: id,
      );
}

Future<void> openLoginGate(
  BuildContext context, {
  required AuthIntent intent,
}) {
  return Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => LoginScreen(intent: intent),
    ),
  );
}

bool isStaffRole(String? role) =>
    role == 'superadmin' || role == 'admin' || role == 'moderator';

/// After successful auth, restore the guest's intended destination.
Future<void> resumeAfterAuth(
  BuildContext context, {
  required Map<String, dynamic> user,
  AuthIntent? intent,
}) async {
  final role = user['role']?.toString();
  if (isStaffRole(role) &&
      (intent == null || intent.action == AuthAction.browse)) {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => AdminPanelScreen(user: user)),
      (_) => false,
    );
    return;
  }

  Navigator.of(context).pushAndRemoveUntil(
    MaterialPageRoute(builder: (_) => HomeScreen(user: user)),
    (_) => false,
  );

  if (intent == null || intent.action == AuthAction.browse) return;
  if (!context.mounted) return;

  switch (intent.action) {
    case AuthAction.createListing:
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => CreateListingScreen(user: user)),
      );
      return;
    case AuthAction.messages:
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => MessagesInboxScreen(user: user)),
      );
      return;
    case AuthAction.trades:
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => TradesScreen(user: user)),
      );
      return;
    case AuthAction.profile:
      // Home already shows guest→auth profile entry; stay on home.
      return;
    case AuthAction.trade:
    case AuthAction.message:
      final lid = intent.listingId;
      if (lid == null) return;
      try {
        final listing = await api.getListing(lid);
        if (!context.mounted) return;
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ListingDetailScreen(
              listing: listing,
              user: user,
              autoStartMessage: intent.action == AuthAction.message,
            ),
          ),
        );
      } catch (_) {
        // Listing may be unavailable; user remains on home.
      }
      return;
    case AuthAction.browse:
      return;
  }
}
