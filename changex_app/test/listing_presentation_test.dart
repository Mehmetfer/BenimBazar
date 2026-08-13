import 'package:changex/listing_presentation/presentation.dart';
import 'package:changex/listing_presentation/schemas.dart';
import 'package:changex/widgets/listing_presentation_layout.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Map<String, dynamic> sample({
    String category = 'Mobilya',
    Map<String, dynamic>? attributes,
    String status = 'APPROVED',
  }) {
    return {
      'id': 1,
      'title': 'KOLTUK (RATTAN)',
      'category': category,
      'subcategory': 'Yatak Odası',
      'description': 'Rattan tek kişilik koltuk.',
      'location_city': 'Adana',
      'location_district': 'Adana',
      'brand': 'Rattan',
      'attributes': attributes ??
          {
            'YIL': '2020 MODEL',
            'OTURUM': 'TEK KİŞİLİK',
            'MALZEME': 'DOĞAL RATTAN',
            'RENK': 'KAHVERENGİ / YEŞİL',
            'DURUM': 'İYİ',
          },
      'status': status,
      'created_at': 1786579200, // 2026-08-13 approx UTC
      'value': {'madalyon': 0},
      'photo_urls': const <String>[],
      'presentation': null,
    };
  }

  test('schema normalize covers major categories', () {
    expect(normalizeCategory('Araç'), 'vehicle');
    expect(normalizeCategory('Mobilya'), 'furniture');
    expect(normalizeCategory('Telefon'), 'phone');
    expect(normalizeCategory('Elektronik'), 'electronics');
    expect(normalizeCategory('Gayrimenkul'), 'real_estate');
    expect(normalizeCategory('Uzay'), 'other');
  });

  test('furniture presentation hero + trade', () {
    final p = buildListingPresentation(sample());
    expect(p.schemaId, 'furniture');
    expect(p.title.toUpperCase(), contains('KOLTUK'));
    expect(p.tradeOpen, isTrue);
    expect(p.heroStats.length, greaterThan(0));
    expect(p.createdLabel, contains('2026'));
  });

  test('vehicle presentation attributes', () {
    final listing = sample(
      category: 'Araç',
      attributes: {
        'YIL': '2015',
        'VITES': 'OTOMATİK',
        'KM': '127.000',
        'YAKIT': 'BENZİN',
      },
    );
    listing['title'] = 'MERCEDES BENZ A180 AMG';
    final p = buildListingPresentation(listing);
    expect(p.schemaId, 'vehicle');
    expect(p.heroStats.map((e) => e.value).join(' '), contains('2015'));
  });

  testWidgets('ListingDetailLayout renders sections', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: ListingDetailLayout(listing: sample()),
          ),
        ),
      ),
    );
    expect(find.textContaining('KOLTUK'), findsWidgets);
    expect(find.text('AÇIKLAMA'), findsOneWidget);
    expect(find.text('ÖZELLİKLER'), findsOneWidget);
    expect(find.text('İLETİŞİM'), findsOneWidget);
    expect(find.text('GÜVENLİ TAKAS'), findsOneWidget);
    expect(find.textContaining('TAKASLARA AÇIK'), findsOneWidget);
  });

  testWidgets('ListingPresentationCard tap', (tester) async {
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListingPresentationCard(
            listing: sample(),
            onTap: () => taps++,
          ),
        ),
      ),
    );
    await tester.tap(find.textContaining('KOLTUK'));
    expect(taps, 1);
  });
}
