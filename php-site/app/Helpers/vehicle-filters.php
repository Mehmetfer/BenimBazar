<?php
declare(strict_types=1);

/** Araç kategori segmentleri (ana sayfa chip / ikon). */
function cx_vehicle_segments(): array
{
    return [
        'tum-araclar' => ['label' => 'Tüm Araçlar', 'icon' => '🔎', 'categories' => ['Araçlar'], 'all_vehicles' => true],
        'otomobil' => ['label' => 'Otomobil', 'icon' => '🚗', 'categories' => ['Araçlar']],
        'motosiklet' => ['label' => 'Motosiklet', 'icon' => '🏍️', 'categories' => ['Araçlar']],
        'bisiklet' => ['label' => 'Bisiklet', 'icon' => '🚲', 'categories' => ['Araçlar']],
        'ticari' => ['label' => 'Ticari Araç', 'icon' => '🚚', 'categories' => ['Araçlar']],
        'antika-arac' => ['label' => 'Antika Araç', 'icon' => '🏛️', 'categories' => ['Araçlar']],
    ];
}

function cx_vehicle_is_all_mode(string $veh): bool
{
    return $veh === 'tum-araclar' || !empty((cx_vehicle_segments()[$veh]['all_vehicles'] ?? false));
}

function cx_vehicle_browse_active(?string $veh): bool
{
    $veh = trim((string) $veh);
    return $veh !== '' && isset(cx_vehicle_segments()[$veh]);
}

function cx_vehicle_segment_label(string $veh): string
{
    return cx_vehicle_segments()[$veh]['label'] ?? 'Araçlar';
}

/** @return array<string,mixed> */
function cx_vehicle_filters_from_request(?string $veh = null): array
{
    $int = static fn ($k) => isset($_GET[$k]) && $_GET[$k] !== '' ? (int) $_GET[$k] : null;
    $str = static fn ($k) => isset($_GET[$k]) && trim((string) $_GET[$k]) !== '' ? trim((string) $_GET[$k]) : null;
    $arr = static function (string $k): array {
        $raw = $_GET[$k] ?? [];
        if (!is_array($raw)) {
            $raw = $raw !== '' ? [(string) $raw] : [];
        }
        return array_values(array_filter(array_map('trim', $raw)));
    };

    $filters = [
        'price_min' => $int('price_min'),
        'price_max' => $int('price_max'),
        'year_min' => $int('year_min'),
        'year_max' => $int('year_max'),
        'km_min' => $int('km_min'),
        'km_max' => $int('km_max'),
        'cc_min' => $int('cc_min'),
        'cc_max' => $int('cc_max'),
        'hp_min' => $int('hp_min'),
        'hp_max' => $int('hp_max'),
        'make' => (static function () use ($arr, $str): array {
            $fromArr = $arr('make');
            if ($fromArr !== []) {
                return $fromArr;
            }
            $single = $str('make');
            return $single !== null ? [$single] : [];
        })(),
        'model' => $str('model'),
        'fuel' => $arr('fuel'),
        'transmission' => $arr('transmission'),
        'drive' => $arr('drive'),
        'body' => $arr('body'),
        'color' => $arr('color'),
        'doors' => array_map('intval', $arr('doors')),
        'seller_type' => $arr('seller_type'),
        'has_price' => !empty($_GET['has_price']),
        'has_photos' => !empty($_GET['has_photos']),
        'promoted' => !empty($_GET['promoted']),
        'all_models' => !empty($_GET['all_models']),
        'arac_seg' => $str('arac_seg'),
    ];

    if ($veh === 'motosiklet') {
        $filters['moto_type'] = $arr('moto_type');
        $filters['drive_train'] = $arr('drive_train');
        $filters['stroke'] = $arr('stroke');
        $filters['cylinders'] = array_map('intval', $arr('cylinders'));
        $filters['emission'] = $arr('emission');
        $filters['condition'] = $arr('condition');
        $filters['damage'] = $arr('damage');
        $filters['inspection'] = $arr('inspection');
        $filters['listing_kind'] = $arr('listing_kind');
    }
    if ($veh === 'bisiklet') {
        $filters['condition'] = $arr('condition');
        $filters['bike_type'] = $arr('bike_type');
        $filters['frame'] = $arr('frame');
        $filters['wheel'] = $arr('wheel');
    }
    if ($veh === 'antika-arac') {
        $filters['condition'] = $arr('condition');
        $filters['era'] = $arr('era');
    }
    if ($veh === 'ticari') {
        $ct = $str('commercial_type');
        $filters['commercial_type'] = cx_vehicle_commercial_type_valid($ct) ? $ct : null;
    }

    return $filters;
}

function cx_vehicle_filters_active(array $filters): bool
{
    foreach ($filters as $key => $val) {
        if (in_array($key, ['has_price', 'has_photos', 'promoted'], true) && $val) {
            return true;
        }
        if (is_array($val) && $val !== []) {
            return true;
        }
        if (!is_array($val) && $val !== null && $val !== '') {
            return true;
        }
    }
    return false;
}

/** @param array<string,mixed> $filters */
function cx_vehicle_browse_step(string $veh, array $filters): string
{
    if (cx_vehicle_is_all_mode($veh)) {
        return 'listings';
    }

    if ($veh === 'ticari' && empty($filters['commercial_type'])) {
        return 'type';
    }

    $wizardSegments = ['otomobil', 'motosiklet', 'bisiklet', 'antika-arac', 'ticari'];
    if (!in_array($veh, $wizardSegments, true)) {
        return 'listings';
    }

    if (empty($filters['make'])) {
        return 'brand';
    }
    if (empty($filters['model']) && empty($filters['all_models'])) {
        return 'model';
    }

    return 'listings';
}

function cx_vehicle_browse_has_wizard(string $veh): bool
{
    if (cx_vehicle_is_all_mode($veh)) {
        return false;
    }

    return in_array($veh, ['otomobil', 'motosiklet', 'bisiklet', 'antika-arac', 'ticari'], true);
}

/** @param array<string,mixed> $filters */
function cx_vehicle_filter_href(string $veh, string $q = '', array $filters = [], array $overrides = []): string
{
    $merged = array_merge($filters, $overrides);
    $params = ['veh' => $veh];
    if ($q !== '') {
        $params['q'] = $q;
    }
    foreach ($merged as $key => $val) {
        if ($val === null || $val === '' || $val === []) {
            continue;
        }
        if (is_bool($val)) {
            if ($val) {
                $params[$key] = '1';
            }
            continue;
        }
        $params[$key] = $val;
    }
    return '/index.php?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
}

/** Kategori degistirince yalnizca ortak filtreleri koru (fiyat, yil, km…). */
function cx_vehicle_filter_segment_href(string $newVeh, string $q = '', array $filters = []): string
{
    $keep = ['price_min', 'price_max', 'year_min', 'year_max', 'km_min', 'km_max', 'has_price', 'has_photos'];
    $common = [];
    foreach ($keep as $key) {
        if (!empty($filters[$key])) {
            $common[$key] = $filters[$key];
        }
    }
    return cx_vehicle_filter_href($newVeh, $q, $common);
}

/** Sol panel ust — 5 arac segmenti. */
function cx_vehicle_filter_segments_ui(): array
{
    $out = [
        [
            'veh' => 'tum-araclar',
            'label' => 'Tüm Araçlar',
            'icon' => '🔎',
        ],
    ];
    foreach (cx_marketplace_catalog() as $row) {
        $out[] = [
            'veh' => $row['veh'],
            'label' => $row['label'],
            'icon' => $row['icon'] ?? '🚗',
        ];
    }

    return $out;
}

/** Sol panel — aralık filtreleri (Car.gr ince arama). */
function cx_vehicle_filter_ranges(?string $veh = null): array
{
    $ranges = [
        'price' => [
            'label' => 'Fiyat',
            'min_key' => 'price_min',
            'max_key' => 'price_max',
            'min_placeholder' => '0',
            'max_placeholder' => 'Sınırsız',
            'step' => 1000,
            'suffix' => '₺',
            'open' => true,
        ],
        'year' => [
            'label' => 'Model yılı',
            'min_key' => 'year_min',
            'max_key' => 'year_max',
            'min_placeholder' => '1980',
            'max_placeholder' => (string) date('Y'),
            'step' => 1,
            'open' => true,
        ],
        'km' => [
            'label' => 'Kilometre',
            'min_key' => 'km_min',
            'max_key' => 'km_max',
            'min_placeholder' => '0',
            'max_placeholder' => '500.000',
            'step' => 1000,
            'suffix' => 'km',
            'open' => true,
        ],
    ];

    if ($veh === 'motosiklet') {
        $ranges['cc'] = [
            'label' => 'Motor hacmi',
            'min_key' => 'cc_min',
            'max_key' => 'cc_max',
            'min_placeholder' => '50',
            'max_placeholder' => '2000',
            'step' => 50,
            'suffix' => 'cc',
            'open' => true,
        ];
        $ranges['hp'] = [
            'label' => 'Beygir gücü',
            'min_key' => 'hp_min',
            'max_key' => 'hp_max',
            'min_placeholder' => '5',
            'max_placeholder' => '300',
            'step' => 5,
            'suffix' => 'HP',
            'open' => false,
        ];
    }

    return $ranges;
}

/** Sol panel — metin filtreleri (model marka seçicisinde). */
function cx_vehicle_filter_text_fields(?string $veh = null): array
{
    return [];
}

/** Car.gr tarzi checkbox filtre tanimlari (Turkce). */
function cx_vehicle_filter_schema(?string $veh = null): array
{
    if ($veh === 'tum-araclar') {
        return [];
    }

    if ($veh === 'motosiklet') {
        return cx_motorcycle_filter_schema();
    }
    if ($veh === 'bisiklet') {
        return cx_bicycle_filter_schema();
    }
    if ($veh === 'antika-arac') {
        return cx_antique_vehicle_filter_schema();
    }

    return [
        'fuel' => [
            'label' => 'Yakıt tipi',
            'options' => ['Benzin', 'Dizel', 'Hibrit', 'Elektrik', 'LPG'],
        ],
        'transmission' => [
            'label' => 'Vites',
            'options' => ['Manuel', 'Otomatik', 'Yarı otomatik'],
        ],
        'drive' => [
            'label' => 'Çekiş',
            'options' => ['4x4', 'Önden', 'Arkadan'],
        ],
        'body' => [
            'label' => 'Kasa tipi',
            'options' => ['Sedan', 'Hatchback', 'SUV', 'Coupe', 'Cabrio', 'Pick-up', 'Minivan'],
        ],
        'color' => [
            'label' => 'Renk',
            'options' => ['Beyaz', 'Siyah', 'Gri', 'Gümüş', 'Mavi', 'Kırmızı', 'Yeşil', 'Bej'],
        ],
        'doors' => [
            'label' => 'Kapı sayısı',
            'options' => [2, 3, 4, 5],
        ],
        'seller_type' => [
            'label' => 'Satıcı tipi',
            'options' => ['Sahibinden', 'Yetkili galeri', 'Galeri'],
        ],
    ];
}

/** Car.gr motosiklet (Μοτοσυκλέτες) ince arama — Turkce. */
function cx_motorcycle_filter_schema(): array
{
    return [
        'listing_kind' => [
            'label' => 'İlan tipi',
            'options' => ['Satılık', 'Alınır', 'Kiralık'],
        ],
        'condition' => [
            'label' => 'Durum',
            'options' => ['Sıfır', 'İkinci el'],
        ],
        'damage' => [
            'label' => 'Hasar durumu',
            'options' => ['Hasarsız', 'Hasarlı'],
        ],
        'inspection' => [
            'label' => 'Ekspertiz',
            'options' => ['Ekspertizli', 'Ekspertiz bekliyor'],
        ],
        'moto_type' => [
            'label' => 'Motosiklet tipi',
            'options' => [
                'Naked',
                'Supersport',
                'Touring',
                'Scooter',
                'Enduro',
                'Cross',
                'Chopper',
                'Klasik',
                'Adventure',
                'Cafe Racer',
            ],
        ],
        'fuel' => [
            'label' => 'Yakıt tipi',
            'options' => ['Benzin', 'Elektrik', 'Hibrit'],
        ],
        'stroke' => [
            'label' => 'Zamanlama',
            'options' => ['4 zamanlı', '2 zamanlı'],
        ],
        'cylinders' => [
            'label' => 'Silindir sayısı',
            'options' => [1, 2, 3, 4, 6],
        ],
        'transmission' => [
            'label' => 'Şanzıman',
            'options' => ['Manuel', 'Otomatik', 'Yarı otomatik'],
        ],
        'drive_train' => [
            'label' => 'Aktarma',
            'options' => ['Zincir', 'Kayış', 'Mil'],
        ],
        'emission' => [
            'label' => 'Emisyon sınıfı',
            'options' => ['Euro 2', 'Euro 3', 'Euro 4', 'Euro 5'],
        ],
        'color' => [
            'label' => 'Renk',
            'options' => ['Beyaz', 'Siyah', 'Gri', 'Gümüş', 'Mavi', 'Kırmızı', 'Sarı', 'Kahverengi', 'Yeşil'],
        ],
        'seller_type' => [
            'label' => 'Satıcı tipi',
            'options' => ['Sahibinden', 'Galeri', 'Mağaza'],
        ],
    ];
}

/** Bisiklet ince arama. */
function cx_bicycle_filter_schema(): array
{
    return [
        'condition' => [
            'label' => 'Durum',
            'options' => ['Sıfır', 'İkinci el'],
        ],
        'bike_type' => [
            'label' => 'Bisiklet tipi',
            'options' => ['Dağ', 'Yol', 'Şehir', 'BMX', 'Elektrikli', 'Çocuk', 'Gravel'],
        ],
        'frame' => [
            'label' => 'Kadro malzemesi',
            'options' => ['Alüminyum', 'Karbon', 'Çelik', 'Titanyum'],
        ],
        'wheel' => [
            'label' => 'Jant boyutu',
            'options' => ['20"', '24"', '26"', '27.5"', '29"', '700c'],
        ],
        'color' => [
            'label' => 'Renk',
            'options' => ['Beyaz', 'Siyah', 'Gri', 'Mavi', 'Kırmızı', 'Yeşil', 'Turuncu'],
        ],
        'seller_type' => [
            'label' => 'Satıcı tipi',
            'options' => ['Sahibinden', 'Mağaza'],
        ],
    ];
}

/** Antika / klasik arac ince arama. */
function cx_antique_vehicle_filter_schema(): array
{
    $car = cx_vehicle_filter_schema('otomobil');
    $car['era'] = [
        'label' => 'Dönem',
        'options' => ['1950 öncesi', '1950–1970', '1970–1990', '1990–2000'],
    ];
    $car['condition'] = [
        'label' => 'Durum',
        'options' => ['Restorasyonlu', 'Orijinal', 'Proje aracı'],
    ];
    return $car;
}

/** Ilan verme formu — sayisal alanlar. */
function cx_vehicle_form_numeric_fields(?string $segment = null): array
{
    $fields = [
        'vehicle_year' => ['label' => 'Model yılı', 'required' => true, 'min' => 1980, 'max' => 2099],
        'vehicle_km' => ['label' => 'Kilometre', 'required' => true, 'min' => 0],
        'vehicle_engine_cc' => ['label' => 'Motor hacmi (cc)', 'required' => false, 'min' => 0],
        'vehicle_hp' => ['label' => 'Beygir (HP)', 'required' => false, 'min' => 0],
    ];

    if ($segment === 'motosiklet') {
        $fields['vehicle_engine_cc']['required'] = true;
    }
    if ($segment === 'bisiklet') {
        $fields['vehicle_km']['required'] = false;
        $fields['vehicle_km']['label'] = 'Kullanım (km, opsiyonel)';
        unset($fields['vehicle_engine_cc'], $fields['vehicle_hp']);
    }
    if ($segment === 'antika-arac') {
        $fields['vehicle_year']['min'] = 1900;
        $fields['vehicle_year']['label'] = 'Model yılı / dönem';
    }
    if ($segment === 'ticari') {
        $fields['vehicle_commercial_type'] = ['label' => 'Ticari araç türü', 'required' => true];
    }

    return $fields;
}

/** Ilan verme formu — segmente ozel select alanlari. */
function cx_vehicle_form_select_fields(?string $segment = null): array
{
    if ($segment === 'motosiklet') {
        $schema = cx_motorcycle_filter_schema();
        return [
            'vehicle_moto_type' => $schema['moto_type'],
            'vehicle_fuel' => $schema['fuel'],
            'vehicle_stroke' => $schema['stroke'],
            'vehicle_cylinders' => $schema['cylinders'],
            'vehicle_transmission' => $schema['transmission'],
            'vehicle_drive_train' => $schema['drive_train'],
            'vehicle_emission' => $schema['emission'],
            'vehicle_color' => $schema['color'],
            'vehicle_condition' => $schema['condition'],
            'vehicle_damage' => $schema['damage'],
            'seller_type' => $schema['seller_type'],
        ];
    }
    if ($segment === 'bisiklet') {
        $schema = cx_bicycle_filter_schema();
        return [
            'vehicle_bike_type' => $schema['bike_type'],
            'vehicle_frame' => $schema['frame'],
            'vehicle_wheel' => $schema['wheel'],
            'vehicle_color' => $schema['color'],
            'vehicle_condition' => $schema['condition'],
            'seller_type' => $schema['seller_type'],
        ];
    }
    if ($segment === 'antika-arac') {
        $schema = cx_antique_vehicle_filter_schema();
        return [
            'vehicle_fuel' => $schema['fuel'],
            'vehicle_transmission' => $schema['transmission'],
            'vehicle_drive' => $schema['drive'],
            'vehicle_body' => $schema['body'],
            'vehicle_color' => $schema['color'],
            'vehicle_doors' => $schema['doors'],
            'vehicle_era' => $schema['era'],
            'vehicle_condition' => $schema['condition'],
            'seller_type' => $schema['seller_type'],
        ];
    }
    if ($segment === 'ticari') {
        $schema = cx_vehicle_filter_schema();
        $commercialLabels = [];
        foreach (cx_vehicle_commercial_types() as $row) {
            $commercialLabels[] = $row['label'];
        }
        return [
            'vehicle_commercial_type' => [
                'label' => 'Ticari araç türü',
                'options' => $commercialLabels,
            ],
            'vehicle_fuel' => $schema['fuel'],
            'vehicle_transmission' => $schema['transmission'],
            'vehicle_drive' => $schema['drive'],
            'vehicle_body' => $schema['body'],
            'vehicle_color' => $schema['color'],
            'seller_type' => $schema['seller_type'],
        ];
    }

    $schema = cx_vehicle_filter_schema();
    return [
        'vehicle_fuel' => $schema['fuel'],
        'vehicle_transmission' => $schema['transmission'],
        'vehicle_drive' => $schema['drive'],
        'vehicle_body' => $schema['body'],
        'vehicle_color' => $schema['color'],
        'vehicle_doors' => $schema['doors'],
        'seller_type' => $schema['seller_type'],
    ];
}

function cx_vehicle_category_for_segment(string $segment): ?string
{
    $resolved = cx_resolve_listing_category(null, $segment);
    return $resolved['category'] ?? null;
}

/**
 * POST verisinden attrs_json icerigi uretir.
 *
 * @param array<string,mixed> $post
 * @return array{attrs:?array<string,mixed>,segment:?string,category:?string,subcategory:?string,slug:?string,error:?string}
 */
function cx_vehicle_attrs_from_post(array $post): array
{
    $segment = trim((string) ($post['vehicle_segment'] ?? ''));
    if ($segment === '' || !isset(cx_vehicle_segments()[$segment])) {
        return ['attrs' => null, 'segment' => null, 'category' => null, 'subcategory' => null, 'slug' => null, 'error' => null];
    }

    $resolved = cx_resolve_listing_category(null, $segment);
    $category = $resolved['category'] ?? cx_vehicle_category_for_segment($segment);
    if ($category === null) {
        return ['attrs' => null, 'segment' => null, 'category' => null, 'subcategory' => null, 'slug' => null, 'error' => 'Geçersiz araç türü.'];
    }
    $subcategory = $resolved['subcategory'] ?? cx_vehicle_segment_label($segment);
    $slug = $resolved['slug'] ?? null;

    $pick = static fn (string $k) => trim((string) ($post[$k] ?? ''));
    $intOrNull = static function (string $k) use ($post): ?int {
        if (!isset($post[$k]) || $post[$k] === '') {
            return null;
        }
        return (int) $post[$k];
    };

    $year = $intOrNull('vehicle_year');
    $km = $intOrNull('vehicle_km');
    $yearMin = $segment === 'antika-arac' ? 1900 : 1980;
    if ($year === null || $year < $yearMin) {
        return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Model yılı zorunludur.'];
    }
    if ($segment !== 'bisiklet' && ($km === null || $km < 0)) {
        return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Kilometre zorunludur.'];
    }

    $schema = cx_vehicle_filter_schema($segment);
    $vehicle = [
        'year' => $year,
        'km' => $km ?? 0,
    ];

    if ($segment === 'bisiklet') {
        $mmErr = cx_vehicle_assign_make_model($vehicle, $segment, $post);
        if ($mmErr !== null) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => $mmErr];
        }

        foreach ([
            'bike_type' => 'vehicle_bike_type',
            'frame' => 'vehicle_frame',
            'wheel' => 'vehicle_wheel',
            'color' => 'vehicle_color',
            'condition' => 'vehicle_condition',
        ] as $key => $field) {
            $val = $pick($field);
            if ($val !== '' && in_array($val, $schema[$key]['options'], true)) {
                $vehicle[$key] = $val;
            }
        }
    } else {
        $fuel = $pick('vehicle_fuel');
        $transmission = $pick('vehicle_transmission');
        if ($fuel === '' || !in_array($fuel, $schema['fuel']['options'], true)) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Yakıt tipi seçin.'];
        }
        if ($transmission === '' || !in_array($transmission, $schema['transmission']['options'], true)) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Vites / şanzıman tipi seçin.'];
        }
        $vehicle['fuel'] = $fuel;
        $vehicle['transmission'] = $transmission;
    }

    $steeringRaw = $pick('vehicle_steering');
    if ($steeringRaw !== '') {
        $steering = match (strtolower($steeringRaw)) {
            'right', 'sag', 'sağ', 'rhd' => 'Sağ dümen',
            'left', 'sol', 'lhd' => 'Sol dümen',
            default => '',
        };
        if ($steering === '' && (str_contains(mb_strtolower($steeringRaw, 'UTF-8'), 'sağ') || str_contains(mb_strtolower($steeringRaw, 'UTF-8'), 'sag'))) {
            $steering = 'Sağ dümen';
        } elseif ($steering === '' && str_contains(mb_strtolower($steeringRaw, 'UTF-8'), 'sol')) {
            $steering = 'Sol dümen';
        }
        if ($steering !== '') {
            $vehicle['steering'] = $steering;
        }
    } elseif (!empty($post['require_steering'])) {
        return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Dümen (sağ/sol) seçin.'];
    }

    $engineCc = $intOrNull('vehicle_engine_cc');
    if ($segment === 'motosiklet') {
        if ($engineCc === null || $engineCc <= 0) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Motor hacmi (cc) zorunludur.'];
        }
        $vehicle['engine_cc'] = $engineCc;
    } elseif ($engineCc !== null && $engineCc > 0) {
        $vehicle['engine_cc'] = $engineCc;
    }

    $hp = $intOrNull('vehicle_hp');
    if ($hp !== null && $hp > 0) {
        $vehicle['hp'] = $hp;
    }

    if ($segment === 'motosiklet') {
        $mmErr = cx_vehicle_assign_make_model($vehicle, $segment, $post);
        if ($mmErr !== null) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => $mmErr];
        }

        foreach ([
            'moto_type' => 'vehicle_moto_type',
            'stroke' => 'vehicle_stroke',
            'drive_train' => 'vehicle_drive_train',
            'emission' => 'vehicle_emission',
            'condition' => 'vehicle_condition',
            'damage' => 'vehicle_damage',
        ] as $key => $field) {
            $val = $pick($field);
            if ($val !== '' && in_array($val, $schema[$key]['options'], true)) {
                $vehicle[$key] = $val;
            }
        }

        $cyl = $intOrNull('vehicle_cylinders');
        if ($cyl !== null && in_array($cyl, $schema['cylinders']['options'], true)) {
            $vehicle['cylinders'] = $cyl;
        }

        $color = $pick('vehicle_color');
        if ($color !== '' && in_array($color, $schema['color']['options'], true)) {
            $vehicle['color'] = $color;
        }
    } elseif ($segment === 'antika-arac') {
        $mmErr = cx_vehicle_assign_make_model($vehicle, $segment, $post);
        if ($mmErr !== null) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => $mmErr];
        }

        $doors = $intOrNull('vehicle_doors');
        if ($doors !== null && in_array($doors, $schema['doors']['options'], true)) {
            $vehicle['doors'] = $doors;
        }
        foreach (['drive' => 'vehicle_drive', 'body' => 'vehicle_body', 'color' => 'vehicle_color', 'era' => 'vehicle_era', 'condition' => 'vehicle_condition'] as $key => $field) {
            $val = $pick($field);
            if ($val !== '' && in_array($val, $schema[$key]['options'], true)) {
                $vehicle[$key] = $val;
            }
        }
    } elseif ($segment === 'ticari') {
        $ctId = $pick('vehicle_commercial_type');
        if (!cx_vehicle_commercial_type_valid($ctId)) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => 'Ticari araç türü seçin.'];
        }
        $vehicle['commercial_type'] = $ctId;

        $mmErr = cx_vehicle_assign_make_model($vehicle, $segment, $post);
        if ($mmErr !== null) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => $mmErr];
        }

        foreach (['drive' => 'vehicle_drive', 'body' => 'vehicle_body', 'color' => 'vehicle_color'] as $key => $field) {
            $val = $pick($field);
            if ($val !== '' && in_array($val, $schema[$key]['options'], true)) {
                $vehicle[$key] = $val;
            }
        }
    } else {
        $mmErr = cx_vehicle_assign_make_model($vehicle, $segment, $post);
        if ($mmErr !== null) {
            return ['attrs' => null, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => $mmErr];
        }

        $doors = $intOrNull('vehicle_doors');
        if ($doors !== null && in_array($doors, $schema['doors']['options'], true)) {
            $vehicle['doors'] = $doors;
        }

        foreach (['drive' => 'vehicle_drive', 'body' => 'vehicle_body', 'color' => 'vehicle_color'] as $key => $field) {
            $val = $pick($field);
            if ($val !== '' && in_array($val, $schema[$key]['options'], true)) {
                $vehicle[$key] = $val;
            }
        }
    }

    $sellerType = $pick('seller_type');
    $seller = [];
    if ($sellerType !== '' && in_array($sellerType, $schema['seller_type']['options'], true)) {
        $seller['type'] = $sellerType;
    }
    $phone = $pick('seller_phone');
    if ($phone !== '') {
        $seller['phone'] = $phone;
    }
    $website = $pick('seller_website');
    if ($website !== '') {
        $seller['website'] = $website;
    }

    $equipmentRaw = trim((string) ($post['vehicle_equipment'] ?? ''));
    $equipment = [];
    if ($equipmentRaw !== '') {
        foreach (preg_split('/[\r\n,;]+/', $equipmentRaw) ?: [] as $row) {
            $s = trim($row);
            if ($s !== '') {
                $equipment[] = $s;
            }
        }
    }

    $attrs = [
        'segment' => $segment,
        'vehicle' => $vehicle,
    ];
    if ($seller !== []) {
        $attrs['seller'] = $seller;
    }
    if ($equipment !== []) {
        $attrs['equipment'] = $equipment;
    }

    return ['attrs' => $attrs, 'segment' => $segment, 'category' => $category, 'subcategory' => $subcategory, 'slug' => $slug, 'error' => null];
}

/** Kart alt satiri: 45.200 km • 1.499 cc • 220 HP • Hibrit */
function cx_listing_vehicle_summary_line(array $item): string
{
    $v = cx_listing_attrs($item)['vehicle'] ?? [];
    if (!is_array($v)) {
        return '';
    }
    $parts = [];
    if (!empty($v['km'])) {
        $parts[] = number_format((int) $v['km'], 0, ',', '.') . ' km';
    }
    if (!empty($v['engine_cc'])) {
        $parts[] = number_format((int) $v['engine_cc'], 0, ',', '.') . ' cc';
    }
    if (!empty($v['hp'])) {
        $parts[] = (string) $v['hp'] . ' HP';
    }
    if (!empty($v['fuel'])) {
        $parts[] = (string) $v['fuel'];
    }
    return implode(' • ', $parts);
}

/** @param array<string,mixed> $filters */
function cx_listing_matches_vehicle_filters(array $item, array $filters, ?string $veh = null): bool
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $seller = is_array($attrs['seller'] ?? null) ? $attrs['seller'] : [];

    $price = isset($item['price_tl']) ? (float) $item['price_tl'] : null;
    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if (!empty($filters['has_price']) && ($mode !== 'SALE' || $price === null || $price <= 0)) {
        return false;
    }
    if (!empty($filters['has_photos'])) {
        $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]');
        if ($photos === []) {
            return false;
        }
    }
    if ($filters['price_min'] !== null && ($price === null || $price < $filters['price_min'])) {
        return false;
    }
    if ($filters['price_max'] !== null && ($price === null || $price > $filters['price_max'])) {
        return false;
    }

    $year = isset($vehicle['year']) ? (int) $vehicle['year'] : null;
    if ($filters['year_min'] !== null && ($year === null || $year < $filters['year_min'])) {
        return false;
    }
    if ($filters['year_max'] !== null && ($year === null || $year > $filters['year_max'])) {
        return false;
    }

    $km = isset($vehicle['km']) ? (int) $vehicle['km'] : null;
    if ($filters['km_min'] !== null && ($km === null || $km < $filters['km_min'])) {
        return false;
    }
    if ($filters['km_max'] !== null && ($km === null || $km > $filters['km_max'])) {
        return false;
    }

    $cc = isset($vehicle['engine_cc']) ? (int) $vehicle['engine_cc'] : null;
    if ($filters['cc_min'] !== null && ($cc === null || $cc < $filters['cc_min'])) {
        return false;
    }
    if ($filters['cc_max'] !== null && ($cc === null || $cc > $filters['cc_max'])) {
        return false;
    }

    $hp = isset($vehicle['hp']) ? (int) $vehicle['hp'] : null;
    if ($filters['hp_min'] !== null && ($hp === null || $hp < $filters['hp_min'])) {
        return false;
    }
    if ($filters['hp_max'] !== null && ($hp === null || $hp > $filters['hp_max'])) {
        return false;
    }

    $containsNeedle = static function (?string $haystack, string $needle): bool {
        if ($needle === '') {
            return true;
        }
        if ($haystack === null || $haystack === '') {
            return false;
        }
        return mb_stripos($haystack, $needle, 0, 'UTF-8') !== false;
    };

    $selectedMakes = $filters['make'] ?? [];
    if (!is_array($selectedMakes)) {
        $selectedMakes = $selectedMakes !== '' && $selectedMakes !== null ? [(string) $selectedMakes] : [];
    }
    if ($selectedMakes !== []) {
        $listingMake = cx_listing_vehicle_make($item, $veh);
        if ($listingMake === '') {
            return false;
        }
        $matched = false;
        foreach ($selectedMakes as $want) {
            if (cx_vehicle_make_equals((string) $want, $listingMake, (string) ($veh ?? ''))) {
                $matched = true;
                break;
            }
        }
        if (!$matched) {
            return false;
        }
    }
    if (!empty($filters['model'])) {
        $listingModel = cx_listing_vehicle_model($item, $veh);
        if ($listingModel === '') {
            $vehicleModel = (string) ($vehicle['model'] ?? '');
            $listingModel = $vehicleModel !== '' ? $vehicleModel : (string) ($item['title'] ?? '');
        }
        if (!cx_vehicle_model_equals((string) $filters['model'], $listingModel)) {
            return false;
        }
    }

    $matchList = static function (array $selected, ?string $actual): bool {
        if ($selected === []) {
            return true;
        }
        if ($actual === null || $actual === '') {
            return false;
        }
        foreach ($selected as $want) {
            if (mb_strtolower((string) $want, 'UTF-8') === mb_strtolower($actual, 'UTF-8')) {
                return true;
            }
        }
        return false;
    };

    $matchIntList = static function (array $selected, ?int $actual): bool {
        if ($selected === []) {
            return true;
        }
        if ($actual === null) {
            return false;
        }
        return in_array($actual, $selected, true);
    };

    if (!$matchList($filters['fuel'], isset($vehicle['fuel']) ? (string) $vehicle['fuel'] : null)) {
        return false;
    }
    if (!$matchList($filters['transmission'], isset($vehicle['transmission']) ? (string) $vehicle['transmission'] : null)) {
        return false;
    }
    if (!$matchList($filters['drive'], isset($vehicle['drive']) ? (string) $vehicle['drive'] : null)) {
        return false;
    }
    if (!$matchList($filters['body'], isset($vehicle['body']) ? (string) $vehicle['body'] : null)) {
        return false;
    }
    if (!$matchList($filters['color'], isset($vehicle['color']) ? (string) $vehicle['color'] : null)) {
        return false;
    }
    if (!$matchIntList($filters['doors'], isset($vehicle['doors']) ? (int) $vehicle['doors'] : null)) {
        return false;
    }
    if (!$matchList($filters['seller_type'], isset($seller['type']) ? (string) $seller['type'] : null)) {
        return false;
    }

    if ($veh === 'motosiklet') {
        if (!$matchList($filters['moto_type'] ?? [], isset($vehicle['moto_type']) ? (string) $vehicle['moto_type'] : null)) {
            return false;
        }
        if (!$matchList($filters['drive_train'] ?? [], isset($vehicle['drive_train']) ? (string) $vehicle['drive_train'] : null)) {
            return false;
        }
        if (!$matchList($filters['stroke'] ?? [], isset($vehicle['stroke']) ? (string) $vehicle['stroke'] : null)) {
            return false;
        }
        if (!$matchIntList($filters['cylinders'] ?? [], isset($vehicle['cylinders']) ? (int) $vehicle['cylinders'] : null)) {
            return false;
        }
        if (!$matchList($filters['emission'] ?? [], isset($vehicle['emission']) ? (string) $vehicle['emission'] : null)) {
            return false;
        }
        if (!$matchList($filters['condition'] ?? [], isset($vehicle['condition']) ? (string) $vehicle['condition'] : null)) {
            return false;
        }
        if (!$matchList($filters['damage'] ?? [], isset($vehicle['damage']) ? (string) $vehicle['damage'] : null)) {
            return false;
        }
        if (!$matchList($filters['inspection'] ?? [], isset($vehicle['inspection']) ? (string) $vehicle['inspection'] : null)) {
            return false;
        }
    }
    if ($veh === 'bisiklet') {
        if (!$matchList($filters['condition'] ?? [], isset($vehicle['condition']) ? (string) $vehicle['condition'] : null)) {
            return false;
        }
        if (!$matchList($filters['bike_type'] ?? [], isset($vehicle['bike_type']) ? (string) $vehicle['bike_type'] : null)) {
            return false;
        }
        if (!$matchList($filters['frame'] ?? [], isset($vehicle['frame']) ? (string) $vehicle['frame'] : null)) {
            return false;
        }
        if (!$matchList($filters['wheel'] ?? [], isset($vehicle['wheel']) ? (string) $vehicle['wheel'] : null)) {
            return false;
        }
    }
    if ($veh === 'antika-arac') {
        if (!$matchList($filters['condition'] ?? [], isset($vehicle['condition']) ? (string) $vehicle['condition'] : null)) {
            return false;
        }
        if (!$matchList($filters['era'] ?? [], isset($vehicle['era']) ? (string) $vehicle['era'] : null)) {
            return false;
        }
    }
    if ($veh === 'ticari' && !empty($filters['commercial_type'])) {
        $listingType = cx_listing_commercial_type($item);
        if ($listingType !== (string) $filters['commercial_type']) {
            return false;
        }
    }

    if ($veh === 'tum-araclar' && !empty($filters['arac_seg'])) {
        $attrs = cx_listing_attrs($item);
        $storedSeg = trim((string) ($attrs['segment'] ?? ''));
        $wantSeg = (string) $filters['arac_seg'];
        if ($storedSeg !== '' && $storedSeg !== $wantSeg) {
            return false;
        }
        if ($storedSeg === '') {
            $label = cx_vehicle_segment_label($wantSeg);
            if (trim((string) ($item['subcategory'] ?? '')) !== $label) {
                return false;
            }
        }
    }

    return true;
}

function cx_listing_matches_vehicle_segment(array $item, string $veh): bool
{
    if (cx_vehicle_is_all_mode($veh)) {
        if ((string) ($item['category'] ?? '') !== 'Araçlar') {
            return false;
        }
        $attrs = cx_listing_attrs($item);
        $storedSeg = trim((string) ($attrs['segment'] ?? ''));
        if ($storedSeg !== '' && isset(cx_vehicle_segments()[$storedSeg]) && !cx_vehicle_is_all_mode($storedSeg)) {
            return true;
        }
        $sub = trim((string) ($item['subcategory'] ?? ''));

        return in_array($sub, ['Otomobil', 'Motosiklet', 'Bisiklet', 'Ticari Araç', 'Antika Araç'], true)
            || cx_is_vehicle_listing($item);
    }

    $seg = cx_vehicle_segments()[$veh] ?? null;
    if ($seg === null) {
        return false;
    }

    $attrs = cx_listing_attrs($item);
    $storedSeg = trim((string) ($attrs['segment'] ?? ''));
    if ($storedSeg !== '' && $storedSeg === $veh) {
        return true;
    }

    $sub = trim((string) ($item['subcategory'] ?? ''));
    if ($sub === $seg['label']) {
        return true;
    }

    if (!cx_is_vehicle_listing($item)) {
        return false;
    }

    $cat = (string) ($item['category'] ?? '');
    if ($cat !== '' && !in_array($cat, $seg['categories'], true)) {
        return false;
    }

    $hay = mb_strtolower((string) ($item['title'] ?? '') . ' ' . ($item['description'] ?? ''), 'UTF-8');
    $keywords = [
        'motosiklet' => ['motosiklet', 'scooter', 'moped', 'motor', 'yamaha', 'honda'],
        'bisiklet' => ['bisiklet', 'bike', 'bicycle', 'decathlon', 'trek', 'canyon'],
        'ticari' => ['ticari', 'kamyon', 'minibüs', 'panelvan', 'sprinter', 'transit', 'tır'],
        'antika-arac' => ['antika', 'klasik', 'vintage', 'collectible', 'restorasyon'],
        'otomobil' => ['otomobil', 'araba', 'bmw', 'mercedes', 'audi', 'sedan', 'suv'],
    ];
    foreach ($keywords[$veh] ?? [] as $kw) {
        if (str_contains($hay, $kw)) {
            return true;
        }
    }

    return $veh === 'otomobil';
}

/**
 * attrs_json → ilan formu alan değerleri (admin düzenleme ön doldurma).
 *
 * @return array<string, string|int>
 */
function cx_vehicle_form_values_from_attrs(?array $attrs): array
{
    if ($attrs === null || $attrs === []) {
        return [];
    }

    $v = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $seller = is_array($attrs['seller'] ?? null) ? $attrs['seller'] : [];
    $equipment = $attrs['equipment'] ?? [];

    $out = [
        'vehicle_segment' => (string) ($attrs['segment'] ?? ''),
        'vehicle_make' => (string) ($v['make'] ?? ''),
        'vehicle_model' => (string) ($v['model'] ?? ''),
        'vehicle_year' => isset($v['year']) ? (string) $v['year'] : '',
        'vehicle_km' => isset($v['km']) ? (string) $v['km'] : '',
        'vehicle_engine_cc' => isset($v['engine_cc']) ? (string) $v['engine_cc'] : '',
        'vehicle_hp' => isset($v['hp']) ? (string) $v['hp'] : '',
        'vehicle_fuel' => (string) ($v['fuel'] ?? ''),
        'vehicle_transmission' => (string) ($v['transmission'] ?? ''),
        'vehicle_steering' => (string) ($v['steering'] ?? ''),
        'vehicle_commercial_type' => (string) ($v['commercial_type'] ?? ''),
        'vehicle_moto_type' => (string) ($v['moto_type'] ?? ''),
        'vehicle_stroke' => (string) ($v['stroke'] ?? ''),
        'vehicle_cylinders' => isset($v['cylinders']) ? (string) $v['cylinders'] : '',
        'vehicle_drive_train' => (string) ($v['drive_train'] ?? ''),
        'vehicle_emission' => (string) ($v['emission'] ?? ''),
        'vehicle_damage' => (string) ($v['damage'] ?? ''),
        'vehicle_bike_type' => (string) ($v['bike_type'] ?? ''),
        'vehicle_frame' => (string) ($v['frame'] ?? ''),
        'vehicle_wheel' => (string) ($v['wheel'] ?? ''),
        'vehicle_drive' => (string) ($v['drive'] ?? ''),
        'vehicle_body' => (string) ($v['body'] ?? ''),
        'vehicle_doors' => isset($v['doors']) ? (string) $v['doors'] : '',
        'vehicle_era' => (string) ($v['era'] ?? ''),
        'vehicle_color' => (string) ($v['color'] ?? ''),
        'vehicle_condition' => (string) ($v['condition'] ?? ''),
        'seller_type' => (string) ($seller['type'] ?? ''),
        'seller_phone' => (string) ($seller['phone'] ?? ''),
        'seller_website' => (string) ($seller['website'] ?? ''),
    ];

    if (is_array($equipment)) {
        $out['vehicle_equipment'] = implode("\n", array_map('strval', $equipment));
    }

    return $out;
}

/**
 * Admin ilan düzenleme — yalnızca marka zorunlu; diğer alanlar opsiyonel (mevcut attrs ile birleşir).
 *
 * @return array{attrs: ?array<string,mixed>, error: ?string}
 */
function cx_vehicle_attrs_merge_admin(array $post, ?array $existingAttrs): array
{
    $segment = trim((string) ($post['vehicle_segment'] ?? ''));
    if ($segment === '' || !isset(cx_vehicle_segments()[$segment])) {
        return ['attrs' => $existingAttrs, 'error' => null];
    }

    $make = trim((string) ($post['vehicle_make'] ?? ''));
    if ($make === '') {
        return ['attrs' => $existingAttrs, 'error' => null];
    }

    if (!cx_vehicle_brand_in_catalog($make, $segment)) {
        return ['attrs' => null, 'error' => 'Geçerli bir marka seçin.'];
    }

    $attrs = is_array($existingAttrs) ? $existingAttrs : [];
    $attrs['segment'] = $segment;
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $vehicle['make'] = cx_vehicle_canonical_make($make, $segment);

    $model = trim((string) ($post['vehicle_model'] ?? ''));
    if ($model !== '' || trim((string) ($post['vehicle_model_custom'] ?? '')) !== '') {
        $modelPack = cx_vehicle_resolve_model_from_post($post, $segment, $vehicle['make']);
        if ($modelPack['error'] !== null) {
            return ['attrs' => null, 'error' => $modelPack['error']];
        }
        if ($modelPack['model'] !== '') {
            $vehicle['model'] = $modelPack['model'];
        }
    }

    $pick = static fn (string $k): string => trim((string) ($post[$k] ?? ''));
    $intOrNull = static function (string $k) use ($post): ?int {
        if (!isset($post[$k]) || $post[$k] === '') {
            return null;
        }
        return (int) $post[$k];
    };

    foreach ([
        'year' => 'vehicle_year',
        'km' => 'vehicle_km',
        'engine_cc' => 'vehicle_engine_cc',
        'hp' => 'vehicle_hp',
        'doors' => 'vehicle_doors',
        'cylinders' => 'vehicle_cylinders',
    ] as $key => $field) {
        $val = $intOrNull($field);
        if ($val !== null) {
            $vehicle[$key] = $val;
        }
    }

    $schema = cx_vehicle_filter_schema($segment);
    $stringFields = [
        'fuel' => 'vehicle_fuel',
        'transmission' => 'vehicle_transmission',
        'moto_type' => 'vehicle_moto_type',
        'stroke' => 'vehicle_stroke',
        'drive_train' => 'vehicle_drive_train',
        'emission' => 'vehicle_emission',
        'damage' => 'vehicle_damage',
        'bike_type' => 'vehicle_bike_type',
        'frame' => 'vehicle_frame',
        'wheel' => 'vehicle_wheel',
        'drive' => 'vehicle_drive',
        'body' => 'vehicle_body',
        'color' => 'vehicle_color',
        'era' => 'vehicle_era',
        'condition' => 'vehicle_condition',
    ];
    foreach ($stringFields as $key => $field) {
        $val = $pick($field);
        if ($val === '') {
            continue;
        }
        if (isset($schema[$key]['options']) && !in_array($val, $schema[$key]['options'], true)) {
            continue;
        }
        $vehicle[$key] = $val;
    }

    $ctId = $pick('vehicle_commercial_type');
    if ($segment === 'ticari' && $ctId !== '' && cx_vehicle_commercial_type_valid($ctId)) {
        $vehicle['commercial_type'] = $ctId;
    }

    $attrs['vehicle'] = $vehicle;

    $seller = is_array($attrs['seller'] ?? null) ? $attrs['seller'] : [];
    $sellerType = $pick('seller_type');
    if ($sellerType !== '' && isset($schema['seller_type']['options']) && in_array($sellerType, $schema['seller_type']['options'], true)) {
        $seller['type'] = $sellerType;
    }
    $phone = $pick('seller_phone');
    if ($phone !== '') {
        $seller['phone'] = $phone;
    }
    $website = $pick('seller_website');
    if ($website !== '') {
        $seller['website'] = $website;
    }
    if ($seller !== []) {
        $attrs['seller'] = $seller;
    }

    $equipmentRaw = trim((string) ($post['vehicle_equipment'] ?? ''));
    if ($equipmentRaw !== '') {
        $equipment = [];
        foreach (preg_split('/[\r\n,;]+/', $equipmentRaw) ?: [] as $row) {
            $s = trim($row);
            if ($s !== '') {
                $equipment[] = $s;
            }
        }
        if ($equipment !== []) {
            $attrs['equipment'] = $equipment;
        }
    }

    return ['attrs' => $attrs, 'error' => null];
}
