import '../widgets/listing_media.dart';
import 'schemas.dart';

class PresentationStat {
  const PresentationStat({required this.key, required this.value});
  final String key;
  final String value;
}

class ListingPresentation {
  const ListingPresentation({
    required this.schemaId,
    required this.title,
    required this.heroStats,
    required this.tradeLabel,
    required this.tradeOpen,
    required this.metadata,
    required this.attributeRows,
    required this.description,
    required this.createdLabel,
    required this.icon,
  });

  final String schemaId;
  final String title;
  final List<PresentationStat> heroStats;
  final String tradeLabel;
  final bool tradeOpen;
  final List<PresentationStat> metadata;
  final List<PresentationStat> attributeRows;
  final String description;
  final String createdLabel;
  final String icon;
}

Map<String, String> _attrMap(Map<String, dynamic> listing) {
  final raw = Map<String, dynamic>.from(listing['attributes'] as Map? ?? {});
  final out = <String, String>{};
  for (final e in raw.entries) {
    final v = e.value?.toString().trim() ?? '';
    if (v.isNotEmpty) out[e.key.toString().trim().toUpperCase()] = v;
  }
  final brand = listing['brand']?.toString().trim() ?? '';
  final model = listing['model_name']?.toString().trim() ?? '';
  if (brand.isNotEmpty && !out.containsKey('MARKA')) out['MARKA'] = brand;
  if (model.isNotEmpty && !out.containsKey('MODEL')) out['MODEL'] = model;
  final cond = listing['condition']?.toString().trim() ?? '';
  if (cond.isNotEmpty && !out.containsKey('DURUM')) out['DURUM'] = cond;
  final value = Map<String, dynamic>.from(listing['value'] as Map? ?? {});
  if (!out.containsKey('DEGER')) {
    final m = value['madalyon'];
    if (m != null) out['DEGER'] = '$m MADALYON';
  }
  return out;
}

String _location(Map<String, dynamic> listing) {
  final parts = [
    listing['location_city']?.toString().trim() ?? '',
    listing['location_district']?.toString().trim() ?? '',
    listing['location']?.toString().trim() ?? '',
  ].where((e) => e.isNotEmpty).toList();
  if (parts.isEmpty) {
    return listing['location_country']?.toString().trim() ?? '';
  }
  return parts.join(', ');
}

String _delivery(Map<String, dynamic> listing) {
  final p = (listing['trade_preference']?.toString() ?? 'DIRECT_ONLY').toUpperCase();
  switch (p) {
    case 'CHAIN_OK':
      return 'ZİNCİR / DOĞRUDAN';
    case 'CHAIN_ONLY':
      return 'ZİNCİR';
    default:
      return 'DOĞRUDAN';
  }
}

String _createdLabel(Map<String, dynamic> listing) {
  final raw = listing['created_at'];
  final ts = raw is num ? raw.toDouble() : double.tryParse(raw?.toString() ?? '');
  if (ts == null) return '';
  final dt = DateTime.fromMillisecondsSinceEpoch((ts * 1000).round(), isUtc: true).toLocal();
  const months = [
    'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
    'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
  ];
  return '${dt.day} ${months[dt.month - 1]} ${dt.year}';
}

List<PresentationStat> _pick(Map<String, String> attrs, List<String> keys) {
  final rows = <PresentationStat>[];
  for (final k in keys) {
    final v = attrs[k];
    if (v != null && v.trim().isNotEmpty) {
      rows.add(PresentationStat(key: k, value: v));
    }
  }
  return rows;
}

ListingPresentation buildListingPresentation(Map<String, dynamic> listing) {
  final server = listing['presentation'];
  if (server is Map) {
    final hero = <PresentationStat>[
      for (final h in (server['hero_stats'] as List? ?? const []))
        if (h is Map && (h['value']?.toString().trim().isNotEmpty ?? false))
          PresentationStat(
            key: h['key']?.toString() ?? '',
            value: h['value'].toString(),
          ),
    ];
    final meta = <PresentationStat>[
      for (final m in (server['metadata'] as List? ?? const []))
        if (m is Map)
          PresentationStat(
            key: m['label']?.toString() ?? '',
            value: m['value']?.toString() ?? '—',
          ),
    ];
    final attrs = <PresentationStat>[
      for (final a in (server['attribute_rows'] as List? ?? const []))
        if (a is Map && (a['value']?.toString().trim().isNotEmpty ?? false))
          PresentationStat(
            key: a['label']?.toString() ?? a['key']?.toString() ?? '',
            value: a['value'].toString(),
          ),
    ];
    final trade = Map<String, dynamic>.from(server['trade_banner'] as Map? ?? {});
    final schema = schemaForCategory(listing['category']?.toString());
    return ListingPresentation(
      schemaId: server['schema_id']?.toString() ?? schema.id,
      title: server['title']?.toString() ?? listing['title']?.toString() ?? '',
      heroStats: hero,
      tradeLabel: trade['label']?.toString() ?? 'TAKASLARA AÇIK',
      tradeOpen: (trade['code']?.toString() ?? 'OPEN') == 'OPEN',
      metadata: meta,
      attributeRows: attrs,
      description: server['description']?.toString() ??
          listing['description']?.toString() ??
          '',
      createdLabel: server['created_label']?.toString() ?? _createdLabel(listing),
      icon: schema.icon,
    );
  }

  final schema = schemaForCategory(listing['category']?.toString());
  final attrs = _attrMap(listing);
  var hero = _pick(attrs, schema.heroKeys);
  if (hero.isEmpty) {
    for (final k in ['MARKA', 'MODEL', 'DURUM', 'DEGER']) {
      if (attrs[k] != null) hero.add(PresentationStat(key: k, value: attrs[k]!));
      if (hero.length >= 3) break;
    }
  }
  final attrRows = _pick(attrs, schema.attributeKeys);
  final shown = attrRows.map((e) => e.key).toSet();
  for (final e in attrs.entries) {
    if (shown.contains(e.key) || e.key == 'DEGER') continue;
    attrRows.add(PresentationStat(key: e.key, value: e.value));
  }

  final ribbon = resolveListingRibbon(listing);
  final tradeOpen = ribbon == ListingTradeRibbon.none;
  final tradeLabel = tradeOpen ? 'TAKASLARA AÇIK' : ribbonLabel(ribbon);

  final loc = _location(listing);
  return ListingPresentation(
    schemaId: schema.id,
    title: listing['title']?.toString() ?? '',
    heroStats: hero,
    tradeLabel: tradeLabel,
    tradeOpen: tradeOpen,
    metadata: [
      PresentationStat(key: 'KATEGORİ', value: listing['category']?.toString() ?? '—'),
      PresentationStat(
        key: 'ALT KATEGORİ',
        value: (listing['subcategory']?.toString().trim().isNotEmpty ?? false)
            ? listing['subcategory'].toString()
            : '—',
      ),
      PresentationStat(key: 'KONUM', value: loc.isEmpty ? '—' : loc),
      PresentationStat(key: 'TESLİM ŞEKLİ', value: _delivery(listing)),
    ],
    attributeRows: attrRows,
    description: listing['description']?.toString() ?? '',
    createdLabel: _createdLabel(listing),
    icon: schema.icon,
  );
}
