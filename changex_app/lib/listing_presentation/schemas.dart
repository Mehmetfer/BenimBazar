/// Category-agnostic listing presentation schemas (Flutter).
library;

class ListingFieldDef {
  const ListingFieldDef(this.key, this.label);
  final String key;
  final String label;
}

class ListingSchema {
  const ListingSchema({
    required this.id,
    required this.heroKeys,
    required this.attributeKeys,
    required this.createFields,
    this.icon = 'category',
  });

  final String id;
  final List<String> heroKeys;
  final List<String> attributeKeys;
  final List<ListingFieldDef> createFields;
  final String icon;
}

const schemas = <String, ListingSchema>{
  'vehicle': ListingSchema(
    id: 'vehicle',
    heroKeys: ['YIL', 'VITES', 'KM'],
    attributeKeys: ['YIL', 'VITES', 'KM', 'YAKIT', 'MARKA', 'MODEL', 'RENK', 'DURUM'],
    createFields: [
      ListingFieldDef('YIL', 'Model yılı'),
      ListingFieldDef('VITES', 'Vites'),
      ListingFieldDef('KM', 'Kilometre'),
      ListingFieldDef('YAKIT', 'Yakıt'),
      ListingFieldDef('RENK', 'Renk'),
    ],
    icon: 'directions_car',
  ),
  'furniture': ListingSchema(
    id: 'furniture',
    heroKeys: ['YIL', 'OTURUM', 'DEGER'],
    attributeKeys: ['YIL', 'OTURUM', 'MALZEME', 'RENK', 'MARKA', 'DURUM', 'KULLANIM'],
    createFields: [
      ListingFieldDef('YIL', 'Model yılı'),
      ListingFieldDef('OTURUM', 'Oturum / tip'),
      ListingFieldDef('MALZEME', 'Malzeme'),
      ListingFieldDef('RENK', 'Renk'),
      ListingFieldDef('KULLANIM', 'Kullanım'),
    ],
    icon: 'chair',
  ),
  'phone': ListingSchema(
    id: 'phone',
    heroKeys: ['YIL', 'DEPOLAMA', 'DURUM'],
    attributeKeys: ['YIL', 'DEPOLAMA', 'RENK', 'MARKA', 'MODEL', 'DURUM', 'GARANTI'],
    createFields: [
      ListingFieldDef('YIL', 'Model yılı'),
      ListingFieldDef('DEPOLAMA', 'Depolama'),
      ListingFieldDef('RENK', 'Renk'),
      ListingFieldDef('GARANTI', 'Garanti'),
    ],
    icon: 'smartphone',
  ),
  'computer': ListingSchema(
    id: 'computer',
    heroKeys: ['YIL', 'RAM', 'DEPOLAMA'],
    attributeKeys: ['YIL', 'RAM', 'DEPOLAMA', 'ISLEMCI', 'MARKA', 'MODEL', 'DURUM'],
    createFields: [
      ListingFieldDef('YIL', 'Model yılı'),
      ListingFieldDef('RAM', 'RAM'),
      ListingFieldDef('DEPOLAMA', 'Depolama'),
      ListingFieldDef('ISLEMCI', 'İşlemci'),
    ],
    icon: 'laptop',
  ),
  'electronics': ListingSchema(
    id: 'electronics',
    heroKeys: ['YIL', 'BOYUT', 'COZUNURLUK'],
    attributeKeys: ['YIL', 'BOYUT', 'COZUNURLUK', 'MARKA', 'MODEL', 'DURUM'],
    createFields: [
      ListingFieldDef('YIL', 'Model yılı'),
      ListingFieldDef('BOYUT', 'Boyut'),
      ListingFieldDef('COZUNURLUK', 'Çözünürlük'),
    ],
    icon: 'devices',
  ),
  'home': ListingSchema(
    id: 'home',
    heroKeys: ['ODA', 'METREKARE', 'KAT'],
    attributeKeys: ['ODA', 'METREKARE', 'KAT', 'MARKA', 'DURUM'],
    createFields: [
      ListingFieldDef('ODA', 'Oda'),
      ListingFieldDef('METREKARE', 'm²'),
      ListingFieldDef('KAT', 'Kat'),
    ],
    icon: 'home',
  ),
  'real_estate': ListingSchema(
    id: 'real_estate',
    heroKeys: ['ODA', 'METREKARE', 'KAT'],
    attributeKeys: ['ODA', 'METREKARE', 'KAT', 'ISINMA', 'DURUM'],
    createFields: [
      ListingFieldDef('ODA', 'Oda'),
      ListingFieldDef('METREKARE', 'm²'),
      ListingFieldDef('KAT', 'Kat'),
      ListingFieldDef('ISINMA', 'Isınma'),
    ],
    icon: 'apartment',
  ),
  'clothing': ListingSchema(
    id: 'clothing',
    heroKeys: ['BEDEN', 'MARKA', 'DURUM'],
    attributeKeys: ['BEDEN', 'MARKA', 'RENK', 'MALZEME', 'DURUM'],
    createFields: [
      ListingFieldDef('BEDEN', 'Beden'),
      ListingFieldDef('RENK', 'Renk'),
      ListingFieldDef('MALZEME', 'Malzeme'),
    ],
    icon: 'checkroom',
  ),
  'hobby': ListingSchema(
    id: 'hobby',
    heroKeys: ['MARKA', 'YIL', 'DURUM'],
    attributeKeys: ['MARKA', 'MODEL', 'DURUM', 'YIL'],
    createFields: [ListingFieldDef('YIL', 'Yıl')],
    icon: 'sports_esports',
  ),
  'other': ListingSchema(
    id: 'other',
    heroKeys: ['MARKA', 'MODEL', 'DURUM'],
    attributeKeys: ['MARKA', 'MODEL', 'DURUM', 'YIL'],
    createFields: [ListingFieldDef('YIL', 'Yıl')],
    icon: 'category',
  ),
};

String normalizeCategory(String? category) {
  final c = (category ?? 'diğer').trim().toLowerCase();
  const aliases = {
    'araç': 'vehicle',
    'arac': 'vehicle',
    'otomobil': 'vehicle',
    'vehicle': 'vehicle',
    'mobilya': 'furniture',
    'furniture': 'furniture',
    'koltuk': 'furniture',
    'telefon': 'phone',
    'cep telefonu': 'phone',
    'phone': 'phone',
    'bilgisayar': 'computer',
    'computer': 'computer',
    'laptop': 'computer',
    'elektronik': 'electronics',
    'electronics': 'electronics',
    'ev': 'home',
    'home': 'home',
    'gayrimenkul': 'real_estate',
    'real_estate': 'real_estate',
    'emlak': 'real_estate',
    'giyim': 'clothing',
    'moda': 'clothing',
    'clothing': 'clothing',
    'hobi': 'hobby',
    'hobby': 'hobby',
    'spor': 'hobby',
    'diğer': 'other',
    'diger': 'other',
    'other': 'other',
  };
  return aliases[c] ?? 'other';
}

ListingSchema schemaForCategory(String? category) =>
    schemas[normalizeCategory(category)] ?? schemas['other']!;

const createCategoryOptions = <String>[
  'Elektronik',
  'Telefon',
  'Bilgisayar',
  'Mobilya',
  'Araç',
  'Ev',
  'Gayrimenkul',
  'Giyim',
  'Hobi',
  'Diğer',
];
