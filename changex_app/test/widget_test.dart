import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:changex/main.dart';
import 'package:changex/screens/create_listing_screen.dart';
import 'package:changex/screens/edit_listing_screen.dart';
import 'package:changex/screens/listing_detail_screen.dart';
import 'package:changex/screens/login_screen.dart';
import 'package:changex/screens/my_listings_screen.dart';
import 'package:changex/screens/splash_screen.dart';
import 'package:changex/widgets/listing_media.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    // Avoid network font fetches flaking widget tests.
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  Future<void> pumpApp(WidgetTester tester, Widget home) async {
    await tester.binding.setSurfaceSize(const Size(400, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: home,
        theme: ThemeData(useMaterial3: true, brightness: Brightness.dark),
      ),
    );
  }

  testWidgets('CHANGE X splash shows brand', (tester) async {
    await tester.pumpWidget(const ChangeXApp());
    expect(find.textContaining('CHANGE'), findsWidgets);
    expect(find.text('X'), findsOneWidget);
    // Splash no longer auto-leaves when session is empty — brand stays.
    await tester.pump(const Duration(milliseconds: 2000));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('X'), findsOneWidget);
    expect(find.text('Giriş / Kayıt'), findsOneWidget);
    expect(find.text('Yönetim Paneli'), findsOneWidget);
  });

  testWidgets('splash opens login without auto-skipping', (tester) async {
    await pumpApp(tester, const SplashScreen());
    await tester.pump(); // start animation
    await tester.pump(const Duration(milliseconds: 1500));
    expect(find.text('Yönetim Paneli'), findsOneWidget);
    await tester.tap(find.text('Giriş / Kayıt'));
    await tester.pumpAndSettle();
    expect(find.text('Takas için hesabına giriş yap'), findsOneWidget);
    expect(find.text('Giriş yap'), findsOneWidget);
  });

  testWidgets('login screen shows yönetim entry and fields', (tester) async {
    await pumpApp(tester, const LoginScreen());
    expect(find.text('Kullanıcı adı'), findsOneWidget);
    expect(find.text('Şifre'), findsOneWidget);
    expect(find.text('Giriş yap'), findsOneWidget);
    expect(find.text('Yönetim paneli girişi'), findsOneWidget);
    expect(find.textContaining('PARA YOK'), findsWidgets);
  });

  testWidgets('create listing shows photo-first picker UI', (tester) async {
    await pumpApp(
      tester,
      CreateListingScreen(user: {'id': 1, 'username': 'tester', 'role': 'user'}),
    );
    expect(find.text('ÜRÜN FOTOĞRAFI EKLE'), findsOneWidget);
    expect(find.text('Galeriden'), findsOneWidget);
    expect(find.text('Kamera'), findsOneWidget);
    expect(find.text('Fotoğraflı ilanı onaya gönder'), findsOneWidget);
    // Submit without photos surfaces validation (not swallowed).
    final submit = find.text('Fotoğraflı ilanı onaya gönder');
    await tester.dragUntilVisible(
      submit,
      find.byType(ListView),
      const Offset(0, -120),
    );
    await tester.pump();
    await tester.tap(submit);
    await tester.pump();
    expect(find.text('En az 1 ürün fotoğrafı ekleyin'), findsOneWidget);
  });

  testWidgets('my listings screen loads for owner', (tester) async {
    await pumpApp(
      tester,
      MyListingsScreen(user: {'id': 1, 'username': 'tester', 'role': 'user'}),
    );
    expect(find.text('İlanlarım'), findsOneWidget);
    // Network unavailable in widget tests → error or empty after settle.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    // Must not crash; either loading finished into empty/error content.
    expect(tester.takeException(), isNull);
    expect(find.text('İlanlarım'), findsOneWidget);
  });

  testWidgets('listing detail requires approved own listing for offer', (tester) async {
    final listing = {
      'id': 42,
      'title': 'Hedef İlan',
      'description': 'Açıklama',
      'category': 'Elektronik',
      'status': 'APPROVED',
      'photo_urls': <String>[],
      'value': {
        'madalyon': 1,
        'dirhem': 0,
        'mandal': 0,
        'total_mandal': 64516,
        'display': '1 Madalyon',
      },
      'owner': {'id': 9, 'username': 'other', 'change_score': 50},
      'wanted_items': 'telefon',
    };
    await pumpApp(
      tester,
      ListingDetailScreen(
        listing: listing,
        user: {'id': 1, 'username': 'tester', 'role': 'user'},
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Takas teklifi ver'), findsOneWidget);
    expect(
      find.textContaining('Yalnızca onaylanmış kendi ilanlarınızla'),
      findsOneWidget,
    );
    // myListings fails offline → empty approved list CTA
    expect(find.textContaining('Onaylı ilanınız yok'), findsOneWidget);
    expect(find.text('Fotoğraflı ilan oluştur'), findsOneWidget);
  });

  testWidgets('edit listing shows photo management chrome', (tester) async {
    await pumpApp(
      tester,
      EditListingScreen(
        user: {'id': 1, 'username': 'tester', 'role': 'user'},
        listing: {
          'id': 7,
          'title': 'Düzenlenecek',
          'description': 'desc',
          'wanted_items': 'x',
          'location': 'İstanbul',
          'version': 1,
          'photo_urls': ['/uploads/a.png', '/uploads/b.png'],
          'status': 'APPROVED',
        },
      ),
    );
    expect(find.text('İlanı düzenle'), findsOneWidget);
    expect(find.text('Fotoğraflar'), findsOneWidget);
    expect(find.text('Kaydet'), findsOneWidget);
    expect(find.byIcon(Icons.add_a_photo_outlined), findsOneWidget);
  });

  testWidgets('listing hero shows gallery controls for multiple photos', (tester) async {
    await pumpApp(
      tester,
      Scaffold(
        body: ListingHeroMedia(
          listing: {
            'status': 'APPROVED',
            'photo_urls': [
              'https://example.test/one.jpg',
              'https://example.test/two.jpg',
              'https://example.test/three.jpg',
            ],
          },
          height: 220,
        ),
      ),
    );
    await tester.pump();
    expect(find.text('1/3'), findsOneWidget);
    expect(find.byIcon(Icons.chevron_left), findsOneWidget);
    expect(find.byIcon(Icons.chevron_right), findsOneWidget);
    // Advance via chevron — PageController animate
    await tester.tap(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    expect(find.text('2/3'), findsOneWidget);
  });

  testWidgets('resolvePhotoUrls survives non-http Uri.base (file:// tests)', (tester) async {
    // Regression: Uri.base.origin previously threw under file:// and crashed UI.
    final urls = resolvePhotoUrls({
      'photo_urls': ['/uploads/a.jpg', 'https://cdn.example/b.jpg'],
    });
    expect(urls.length, 2);
    expect(urls[0], '/uploads/a.jpg'); // relative kept when origin unavailable
    expect(urls[1], 'https://cdn.example/b.jpg');
  });

  testWidgets('create listing photo preview area is tappable gallery CTA', (tester) async {
    await pumpApp(
      tester,
      CreateListingScreen(user: {'id': 1, 'username': 'tester', 'role': 'user'}),
    );
    expect(find.byIcon(Icons.add_a_photo_outlined), findsWidgets);
    expect(find.textContaining('en fazla 9 fotoğraf'), findsOneWidget);
    // Tapping hero CTA should invoke picker (platform may cancel) without crash.
    await tester.tap(find.text('ÜRÜN FOTOĞRAFI EKLE'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(tester.takeException(), isNull);
  });
}
