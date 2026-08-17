<?php
declare(strict_types=1);

use App\Services\ListingService;

/** @return array{name:string,domain:string,popular:bool,aliases?:list<string>} */
function cx_vehicle_brand_row(string $name, string $domain, bool $popular = false, array $aliases = []): array
{
    return ['name' => $name, 'domain' => $domain, 'popular' => $popular, 'aliases' => $aliases];
}

/** @return list<array{name:string,domain:string,popular:bool,aliases?:list<string>}> */
function cx_vehicle_brand_catalog(string $veh): array
{
    static $cache = [];
    if (isset($cache[$veh])) {
        return $cache[$veh];
    }

    $otomobil = [
        cx_vehicle_brand_row('Audi', 'audi.com', true),
        cx_vehicle_brand_row('BMW', 'bmw.com', true),
        cx_vehicle_brand_row('Citroën', 'citroen.com', true, ['Citroen']),
        cx_vehicle_brand_row('Fiat', 'fiat.com', true),
        cx_vehicle_brand_row('Ford', 'ford.com', true),
        cx_vehicle_brand_row('Hyundai', 'hyundai.com', true),
        cx_vehicle_brand_row('Mercedes-Benz', 'mercedes-benz.com', true, ['Mercedes', 'Mercedes Benz']),
        cx_vehicle_brand_row('Mini', 'mini.com', true),
        cx_vehicle_brand_row('Nissan', 'nissan.com', true),
        cx_vehicle_brand_row('Opel', 'opel.com', true),
        cx_vehicle_brand_row('Peugeot', 'peugeot.com', true),
        cx_vehicle_brand_row('Renault', 'renault.com', true),
        cx_vehicle_brand_row('Suzuki', 'suzuki.com', true),
        cx_vehicle_brand_row('Toyota', 'toyota.com', true),
        cx_vehicle_brand_row('Volkswagen', 'volkswagen.com', true, ['VW']),
        cx_vehicle_brand_row('Abarth', 'abarth.com'),
        cx_vehicle_brand_row('Alfa Romeo', 'alfaromeo.com'),
        cx_vehicle_brand_row('Aston Martin', 'astonmartin.com'),
        cx_vehicle_brand_row('Bentley', 'bentley.com'),
        cx_vehicle_brand_row('BYD', 'byd.com'),
        cx_vehicle_brand_row('Cadillac', 'cadillac.com'),
        cx_vehicle_brand_row('Chevrolet', 'chevrolet.com'),
        cx_vehicle_brand_row('Chrysler', 'chrysler.com'),
        cx_vehicle_brand_row('Cupra', 'cupra.com'),
        cx_vehicle_brand_row('Dacia', 'dacia.com'),
        cx_vehicle_brand_row('Daewoo', 'daewoo.com'),
        cx_vehicle_brand_row('Daihatsu', 'daihatsu.com'),
        cx_vehicle_brand_row('Dodge', 'dodge.com'),
        cx_vehicle_brand_row('DS', 'dsautomobiles.com'),
        cx_vehicle_brand_row('Ferrari', 'ferrari.com'),
        cx_vehicle_brand_row('Honda', 'honda.com'),
        cx_vehicle_brand_row('Hummer', 'hummer.com'),
        cx_vehicle_brand_row('Infiniti', 'infiniti.com'),
        cx_vehicle_brand_row('Isuzu', 'isuzu.com'),
        cx_vehicle_brand_row('Jaguar', 'jaguar.com'),
        cx_vehicle_brand_row('Jeep', 'jeep.com'),
        cx_vehicle_brand_row('Kia', 'kia.com'),
        cx_vehicle_brand_row('Lada', 'lada.ru'),
        cx_vehicle_brand_row('Lamborghini', 'lamborghini.com'),
        cx_vehicle_brand_row('Lancia', 'lancia.com'),
        cx_vehicle_brand_row('Land Rover', 'landrover.com'),
        cx_vehicle_brand_row('Lexus', 'lexus.com'),
        cx_vehicle_brand_row('Maserati', 'maserati.com'),
        cx_vehicle_brand_row('Mazda', 'mazda.com'),
        cx_vehicle_brand_row('McLaren', 'mclaren.com'),
        cx_vehicle_brand_row('MG', 'mg.co.uk'),
        cx_vehicle_brand_row('Mitsubishi', 'mitsubishi.com'),
        cx_vehicle_brand_row('Porsche', 'porsche.com'),
        cx_vehicle_brand_row('Rolls Royce', 'rolls-royce.com', false, ['Rolls-Royce']),
        cx_vehicle_brand_row('Rover', 'rover.com'),
        cx_vehicle_brand_row('Saab', 'saab.com'),
        cx_vehicle_brand_row('Seat', 'seat.com'),
        cx_vehicle_brand_row('Skoda', 'skoda-auto.com', false, ['Škoda']),
        cx_vehicle_brand_row('Smart', 'smart.com'),
        cx_vehicle_brand_row('Subaru', 'subaru.com'),
        cx_vehicle_brand_row('Tesla', 'tesla.com'),
        cx_vehicle_brand_row('Togg', 'togg.com.tr'),
        cx_vehicle_brand_row('Volvo', 'volvocars.com'),
        cx_vehicle_brand_row('Diğer', 'example.com'),
    ];

    $motosiklet = [
        cx_vehicle_brand_row('Honda', 'honda.com', true),
        cx_vehicle_brand_row('Yamaha', 'yamaha-motor.com', true),
        cx_vehicle_brand_row('Kawasaki', 'kawasaki.com', true),
        cx_vehicle_brand_row('Suzuki', 'suzuki.com', true),
        cx_vehicle_brand_row('BMW', 'bmw.com', true),
        cx_vehicle_brand_row('Ducati', 'ducati.com', true),
        cx_vehicle_brand_row('KTM', 'ktm.com', true),
        cx_vehicle_brand_row('Harley-Davidson', 'harley-davidson.com', true),
        cx_vehicle_brand_row('Aprilia', 'aprilia.com'),
        cx_vehicle_brand_row('Benelli', 'benelli.com'),
        cx_vehicle_brand_row('Husqvarna', 'husqvarna-motorcycles.com'),
        cx_vehicle_brand_row('Indian', 'indianmotorcycle.com'),
        cx_vehicle_brand_row('Piaggio', 'piaggio.com'),
        cx_vehicle_brand_row('Royal Enfield', 'royalenfield.com'),
        cx_vehicle_brand_row('Triumph', 'triumphmotorcycles.com'),
        cx_vehicle_brand_row('Vespa', 'vespa.com'),
        cx_vehicle_brand_row('Diğer', 'example.com'),
    ];

    $bisiklet = [
        cx_vehicle_brand_row('Trek', 'trekbikes.com', true),
        cx_vehicle_brand_row('Giant', 'giant-bicycles.com', true),
        cx_vehicle_brand_row('Specialized', 'specialized.com', true),
        cx_vehicle_brand_row('Cannondale', 'cannondale.com', true),
        cx_vehicle_brand_row('Bianchi', 'bianchi.com', true),
        cx_vehicle_brand_row('Cube', 'cube.eu', true),
        cx_vehicle_brand_row('Decathlon', 'decathlon.com', true),
        cx_vehicle_brand_row('Scott', 'scott-sports.com'),
        cx_vehicle_brand_row('Merida', 'merida-bikes.com'),
        cx_vehicle_brand_row('Canyon', 'canyon.com'),
        cx_vehicle_brand_row('Diğer', 'example.com'),
    ];

    $ticari = [
        cx_vehicle_brand_row('Ford', 'ford.com', true),
        cx_vehicle_brand_row('Mercedes-Benz', 'mercedes-benz.com', true, ['Mercedes']),
        cx_vehicle_brand_row('Volkswagen', 'volkswagen.com', true, ['VW']),
        cx_vehicle_brand_row('Fiat', 'fiat.com', true),
        cx_vehicle_brand_row('Isuzu', 'isuzu.com', true),
        cx_vehicle_brand_row('Renault', 'renault.com', true),
        cx_vehicle_brand_row('Iveco', 'iveco.com'),
        cx_vehicle_brand_row('MAN', 'man.eu'),
        cx_vehicle_brand_row('Peugeot', 'peugeot.com'),
        cx_vehicle_brand_row('Scania', 'scania.com'),
        cx_vehicle_brand_row('Volvo', 'volvocars.com'),
        cx_vehicle_brand_row('Diğer', 'example.com'),
    ];

    $antika = [
        cx_vehicle_brand_row('Mercedes-Benz', 'mercedes-benz.com', true, ['Mercedes']),
        cx_vehicle_brand_row('Ford', 'ford.com', true),
        cx_vehicle_brand_row('Volkswagen', 'volkswagen.com', true, ['VW']),
        cx_vehicle_brand_row('Cadillac', 'cadillac.com', true),
        cx_vehicle_brand_row('Porsche', 'porsche.com', true),
        cx_vehicle_brand_row('BMW', 'bmw.com'),
        cx_vehicle_brand_row('Chevrolet', 'chevrolet.com'),
        cx_vehicle_brand_row('Fiat', 'fiat.com'),
        cx_vehicle_brand_row('Jaguar', 'jaguar.com'),
        cx_vehicle_brand_row('Rolls Royce', 'rolls-royce.com', false, ['Rolls-Royce']),
        cx_vehicle_brand_row('Diğer', 'example.com'),
    ];

    $map = [
        'otomobil' => $otomobil,
        'motosiklet' => $motosiklet,
        'bisiklet' => $bisiklet,
        'ticari' => $ticari,
        'antika-arac' => $antika,
    ];

    $cache[$veh] = $map[$veh] ?? $otomobil;
    return $cache[$veh];
}

function cx_vehicle_brand_icon_slug(string $name): string
{
    static $map = [
        'Mercedes-Benz' => 'mercedes',
        'Mercedes' => 'mercedes',
        'Mercedes Benz' => 'mercedes',
        'Volkswagen' => 'volkswagen',
        'VW' => 'volkswagen',
        'Citroën' => 'citroen',
        'Citroen' => 'citroen',
        'Alfa Romeo' => 'alfaromeo',
        'Aston Martin' => 'astonmartin',
        'Land Rover' => 'landrover',
        'Rolls Royce' => 'rollsroyce',
        'Rolls-Royce' => 'rollsroyce',
        'Harley-Davidson' => 'harleydavidson',
        'Royal Enfield' => 'royalenfield',
        'Skoda' => 'skoda',
        'Škoda' => 'skoda',
        'DS' => 'dsautomobiles',
        'Mini' => 'mini',
        'Seat' => 'seat',
        'MG' => 'mg',
        'BYD' => 'byd',
        'Togg' => 'togg',
        'MAN' => 'man',
        'Yamaha' => 'yamaha',
        'Kawasaki' => 'kawasaki',
        'Indian' => 'indianmotorcycle',
        'Diğer' => '',
    ];

    if (isset($map[$name])) {
        return $map[$name];
    }

    $slug = mb_strtolower($name, 'UTF-8');
    $slug = strtr($slug, ['ö' => 'o', 'ü' => 'u', 'ş' => 's', 'ı' => 'i', 'ğ' => 'g', 'ç' => 'c', ' ' => '', '-' => '']);
    return preg_replace('/[^a-z0-9]/', '', $slug) ?? '';
}

/** @return list<string> */
function cx_vehicle_brand_logo_paths(string $name, string $domain): array
{
    if ($name === 'Diğer' || $domain === 'example.com') {
        return [];
    }

    $slug = cx_vehicle_brand_icon_slug($name);
    $paths = [];
    $base = defined('BASE_PATH') ? BASE_PATH : dirname(__DIR__, 2);

    if ($slug !== '') {
        foreach (['svg', 'png', 'webp'] as $ext) {
            $file = $base . '/assets/brands/' . $slug . '.' . $ext;
            if (is_file($file)) {
                $paths[] = '/assets/brands/' . $slug . '.' . $ext . '?v=20260814';
            }
        }
        if ($paths === []) {
            $paths[] = 'https://cdn.simpleicons.org/' . rawurlencode($slug) . '/406367';
        }
    }

    $paths[] = 'https://www.google.com/s2/favicons?domain=' . rawurlencode($domain) . '&sz=128';
    $paths[] = 'https://icons.duckduckgo.com/ip3/' . rawurlencode($domain) . '.ico';

    return array_values(array_unique($paths));
}

function cx_vehicle_brand_logo_url(string $domain, string $name = ''): string
{
    $paths = cx_vehicle_brand_logo_paths($name !== '' ? $name : $domain, $domain);
    return $paths[0] ?? '';
}

/** @param array<string,mixed> $brand */
function cx_vehicle_brand_logo_attrs(array $brand): string
{
    $name = (string) ($brand['name'] ?? '');
    $domain = (string) ($brand['domain'] ?? '');
    $paths = cx_vehicle_brand_logo_paths($name, $domain);
    if ($paths === []) {
        return '';
    }
    $src = array_shift($paths);
    $fallbacks = htmlspecialchars(implode('|', $paths), ENT_QUOTES, 'UTF-8');
    $srcEsc = htmlspecialchars($src, ENT_QUOTES, 'UTF-8');
    return 'src="' . $srcEsc . '" data-fallbacks="' . $fallbacks . '" data-fallback-idx="0" onerror="cxBrandLogoFallback(this)"';
}

function cx_vehicle_normalize_make_token(string $value): string
{
    $v = mb_strtolower(trim($value), 'UTF-8');
    $v = str_replace(['-', '_', '.'], ' ', $v);
    $v = preg_replace('/\s+/u', ' ', $v) ?? $v;
    return trim($v);
}

function cx_vehicle_canonical_make(string $raw, string $veh): string
{
    $raw = trim($raw);
    if ($raw === '') {
        return '';
    }
    $needle = cx_vehicle_normalize_make_token($raw);
    foreach (cx_vehicle_brand_catalog($veh) as $brand) {
        if (cx_vehicle_normalize_make_token($brand['name']) === $needle) {
            return $brand['name'];
        }
        foreach ($brand['aliases'] ?? [] as $alias) {
            if (cx_vehicle_normalize_make_token($alias) === $needle) {
                return $brand['name'];
            }
        }
    }
    return $raw;
}

function cx_vehicle_make_equals(string $selected, string $listingMake, string $veh): bool
{
    $a = cx_vehicle_canonical_make($selected, $veh);
    $b = cx_vehicle_canonical_make($listingMake, $veh);
    return cx_vehicle_normalize_make_token($a) === cx_vehicle_normalize_make_token($b);
}

/** @param array<string,mixed> $item */
function cx_listing_vehicle_make(array $item, ?string $veh = null): string
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $make = trim((string) ($vehicle['make'] ?? ''));
    if ($make !== '') {
        return $veh !== null ? cx_vehicle_canonical_make($make, $veh) : $make;
    }

    if ($veh === null) {
        $veh = trim((string) ($attrs['segment'] ?? ''));
    }
    if ($veh === '') {
        return '';
    }

    $title = (string) ($item['title'] ?? '');
    if ($title === '') {
        return '';
    }
    $hay = mb_strtolower($title, 'UTF-8');
    foreach (cx_vehicle_brand_catalog($veh) as $brand) {
        $names = array_merge([$brand['name']], $brand['aliases'] ?? []);
        foreach ($names as $name) {
            if ($name === 'Diğer') {
                continue;
            }
            if (preg_match('/\b' . preg_quote(mb_strtolower($name, 'UTF-8'), '/') . '\b/u', $hay)) {
                return $brand['name'];
            }
        }
    }
    return '';
}

/** @return array<string,int> */
function cx_vehicle_brand_counts(string $veh, ?string $commercialType = null): array
{
    static $cache = [];
    $key = $veh . '|' . (string) $commercialType;
    if (isset($cache[$key])) {
        return $cache[$key];
    }
    $svc = new ListingService();
    $cache[$key] = $svc->vehicleBrandCounts($veh, $commercialType);
    return $cache[$key];
}

/**
 * @param array<string,mixed> $filters
 * @return array{popular:list<array<string,mixed>>,all:list<array<string,mixed>>,selected:list<string>}
 */
function cx_vehicle_brand_picker_data(string $veh, array $filters): array
{
    $commercialType = ($veh === 'ticari' && !empty($filters['commercial_type']))
        ? (string) $filters['commercial_type']
        : null;
    $counts = cx_vehicle_brand_counts($veh, $commercialType);
    $selected = [];
    $raw = $filters['make'] ?? [];
    if (!is_array($raw)) {
        $raw = $raw !== '' && $raw !== null ? [(string) $raw] : [];
    }
    foreach ($raw as $s) {
        $s = trim((string) $s);
        if ($s !== '') {
            $selected[] = cx_vehicle_canonical_make($s, $veh);
        }
    }
    $selected = array_values(array_unique($selected));

    $rows = [];
    foreach (cx_vehicle_brand_catalog($veh) as $brand) {
        $name = $brand['name'];
        $logoPaths = cx_vehicle_brand_logo_paths($name, $brand['domain']);
        $rows[] = [
            'name' => $name,
            'domain' => $brand['domain'],
            'logo' => $logoPaths[0] ?? '',
            'logo_fallbacks' => array_slice($logoPaths, 1),
            'popular' => !empty($brand['popular']),
            'count' => (int) ($counts[$name] ?? 0),
        ];
    }

    usort($rows, static function (array $a, array $b): int {
        if ($a['count'] !== $b['count']) {
            return $b['count'] <=> $a['count'];
        }
        return strcasecmp($a['name'], $b['name']);
    });

    $popular = [];
    $all = [];
    foreach ($rows as $row) {
        if ($row['popular'] && $row['count'] > 0) {
            $popular[] = $row;
        }
        $all[] = $row;
    }
    if ($popular === []) {
        foreach ($rows as $row) {
            if ($row['popular']) {
                $popular[] = $row;
            }
        }
    }

    return ['popular' => $popular, 'all' => $all, 'selected' => $selected];
}

function cx_vehicle_brand_picker_summary(array $selected): string
{
    if ($selected === []) {
        return 'Marka';
    }
    if (count($selected) === 1) {
        return (string) $selected[0];
    }
    return $selected[0] . ' +' . (count($selected) - 1);
}
