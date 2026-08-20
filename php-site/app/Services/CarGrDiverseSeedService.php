<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;

/**
 * Car.gr tarzı çeşitli marka/model ilanları — mevcut kullanıcılara dağıtır.
 * Idempotent: aynı başlık varsa atlanır.
 */
final class CarGrDiverseSeedService
{
    private const LISTING_NO_BASE = 1000000000;

    /** @return list<string> */
    public static function seed(): array
    {
        $pdo = Database::pdo();
        $messages = [];
        $now = microtime(true);

        $userIds = self::loadExistingUserIds($pdo);
        if ($userIds === []) {
            require_once __DIR__ . '/VehicleMarketSeedService.php';
            foreach (VehicleMarketSeedService::seed() as $m) {
                $messages[] = $m;
            }
            $userIds = self::loadExistingUserIds($pdo);
            if ($userIds === []) {
                $messages[] = 'HATA: Hic kullanici bulunamadi';
                return $messages;
            }
        }

        $messages[] = count($userIds) . ' mevcut kullaniciya ilan dagitilacak';

        $hasAttrs = (bool) $pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();
        $insertSql = $hasAttrs
            ? 'INSERT INTO trade_listings (
              owner_id, title, description, category, subcategory, location, accept_categories, wanted_items,
              photo_urls, attrs_json, status, listing_mode, price_tl, price_negotiable, mandal_units, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            : 'INSERT INTO trade_listings (
              owner_id, title, description, category, subcategory, location, accept_categories, wanted_items,
              photo_urls, status, listing_mode, price_tl, price_negotiable, mandal_units, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)';

        $insert = $pdo->prepare($insertSql);
        $catalog = self::diverseCatalog();
        $added = 0;
        $skipped = 0;
        $userCount = count($userIds);

        foreach ($catalog as $i => $item) {
            $chk = $pdo->prepare('SELECT id FROM trade_listings WHERE title = ? LIMIT 1');
            $chk->execute([$item['title']]);
            if ($chk->fetch()) {
                $skipped++;
                continue;
            }

            $ownerId = $userIds[$i % $userCount];
            $photos = json_encode($item['photos'], JSON_UNESCAPED_UNICODE);
            $attrs = json_encode($item['attrs'], JSON_UNESCAPED_UNICODE);
            $created = $now - (86400 * random_int(1, 90)) - random_int(0, 86400);

            $params = [
                $ownerId,
                $item['title'],
                $item['description'],
                'Araçlar',
                $item['subcategory'],
                $item['location'],
                '[]',
                $item['wanted'] ?? '',
                $photos,
                ...($hasAttrs ? [$attrs] : []),
                'APPROVED',
                $item['mode'],
                $item['price'],
                $item['negotiable'] ? 1 : 0,
                8 + ($i % 12) * 2,
                $created,
                $created + random_int(3600, 120000),
            ];

            $insert->execute($params);
            $added++;
        }

        $messages[] = $added . ' yeni ilan eklendi, ' . $skipped . ' atlandi (zaten vardi)';
        $messages[] = 'Toplam hedef: ' . count($catalog) . ' car.gr tarzi cesitli marka/model';

        return $messages;
    }

    /** @return list<int> */
    private static function loadExistingUserIds(\PDO $pdo): array
    {
        $stmt = $pdo->query(
            "SELECT id FROM users WHERE suspended = 0 AND role IN ('user','moderator','admin')
             ORDER BY id ASC"
        );
        $ids = [];
        while ($row = $stmt->fetch(\PDO::FETCH_ASSOC)) {
            $ids[] = (int) $row['id'];
        }
        if ($ids !== []) {
            return $ids;
        }

        $fallback = $pdo->query(
            "SELECT id FROM users WHERE role != 'superadmin' ORDER BY id ASC"
        );
        while ($row = $fallback->fetch(\PDO::FETCH_ASSOC)) {
            $ids[] = (int) $row['id'];
        }

        return $ids;
    }

    /** @return list<array<string,mixed>> */
    private static function diverseCatalog(): array
    {
        $cities = ['Istanbul', 'Ankara', 'Izmir', 'Bursa', 'Antalya', 'Adana', 'Konya', 'Gaziantep', 'Mersin', 'Kocaeli'];
        $ci = static fn (int $n): string => $cities[$n % count($cities)];

        $carPhotos = [
            'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=1200',
            'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=1200',
            'https://images.unsplash.com/photo-1542362567-b07e54358753?w=1200',
        ];

        return array_merge(
            self::otomobilDiverse($ci, $carPhotos),
            self::motosikletDiverse($ci),
            self::bisikletDiverse($ci),
            self::ticariDiverse($ci),
            self::antikaDiverse($ci),
        );
    }

    /**
     * @param callable(int): string $city
     * @param list<string> $photos
     * @return list<array<string,mixed>>
     */
    private static function otomobilDiverse(callable $city, array $photos): array
    {
        $rows = [
            ['Renault Clio 1.0 TCe Icon 2023', 685000, 'Clio Icon, 22.000 km, benzin, otomatik. Garantili, hatasiz.', ['year' => 2023, 'km' => 22000, 'fuel' => 'Benzin', 'engine_cc' => 999, 'hp' => 90, 'transmission' => 'Otomatik', 'body' => 'Hatchback', 'doors' => 5, 'color' => 'Turuncu', 'make' => 'Renault', 'model' => 'Clio']],
            ['Peugeot 3008 GT 1.5 BlueHDi 2021', 1425000, '3008 GT, 48.000 km, dizel, EAT8. Panoramik cam tavan, Focal ses.', ['year' => 2021, 'km' => 48000, 'fuel' => 'Dizel', 'engine_cc' => 1499, 'hp' => 130, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Gri', 'make' => 'Peugeot', 'model' => '3008']],
            ['Kia Sportage 1.6 T-GDI Cool 2022', 1285000, 'Sportage Cool, 35.000 km, benzin, otomatik. ADAS paket, deri koltuk.', ['year' => 2022, 'km' => 35000, 'fuel' => 'Benzin', 'engine_cc' => 1598, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Beyaz', 'make' => 'Kia', 'model' => 'Sportage']],
            ['Dacia Duster 1.5 dCi Comfort 2020', 625000, 'Duster 4x2, 89.000 km, dizel. Aile SUV, bakimli.', ['year' => 2020, 'km' => 89000, 'fuel' => 'Dizel', 'engine_cc' => 1461, 'hp' => 115, 'transmission' => 'Manuel', 'body' => 'SUV', 'color' => 'Mavi', 'make' => 'Dacia', 'model' => 'Duster']],
            ['Hyundai Tucson 1.6 T-GDI Elite 2023', 1395000, 'Tucson Elite, 18.000 km. Smart sense, wireless CarPlay.', ['year' => 2023, 'km' => 18000, 'fuel' => 'Benzin', 'engine_cc' => 1598, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Siyah', 'make' => 'Hyundai', 'model' => 'Tucson']],
            ['Opel Corsa 1.2 GS Line 2022', 745000, 'Corsa GS Line, 31.000 km, benzin. LED matrix far, sport paket.', ['year' => 2022, 'km' => 31000, 'fuel' => 'Benzin', 'engine_cc' => 1199, 'hp' => 100, 'transmission' => 'Manuel', 'body' => 'Hatchback', 'color' => 'Kirmizi', 'make' => 'Opel', 'model' => 'Corsa']],
            ['Nissan Qashqai 1.3 DIG-T Platinum 2021', 1185000, 'Qashqai Platinum, 52.000 km. ProPILOT, Around View.', ['year' => 2021, 'km' => 52000, 'fuel' => 'Benzin', 'engine_cc' => 1332, 'hp' => 158, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Gumus', 'make' => 'Nissan', 'model' => 'Qashqai']],
            ['Skoda Octavia 1.5 TSI Style 2020', 985000, 'Octavia Style, 72.000 km, benzin, DSG. Virtual cockpit, ACC.', ['year' => 2020, 'km' => 72000, 'fuel' => 'Benzin', 'engine_cc' => 1498, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'color' => 'Beyaz', 'make' => 'Skoda', 'model' => 'Octavia']],
            ['Seat Leon 1.5 TSI FR 2021', 1050000, 'Leon FR, 44.000 km. Spor suspansiyon, tam LED.', ['year' => 2021, 'km' => 44000, 'fuel' => 'Benzin', 'engine_cc' => 1498, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'Hatchback', 'color' => 'Gri', 'make' => 'Seat', 'model' => 'Leon']],
            ['Volvo XC60 B4 Inscription 2022', 2150000, 'XC60 B4 mild hybrid, 28.000 km. Pilot Assist, Bowers & Wilkins.', ['year' => 2022, 'km' => 28000, 'fuel' => 'Hibrit', 'engine_cc' => 1969, 'hp' => 197, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Lacivert', 'make' => 'Volvo', 'model' => 'XC60']],
            ['Tesla Model 3 Long Range 2023', 1685000, 'Model 3 LR, 24.000 km. Otopilot, beyaz ic, cam tavan.', ['year' => 2023, 'km' => 24000, 'fuel' => 'Elektrik', 'hp' => 366, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'color' => 'Beyaz', 'make' => 'Tesla', 'model' => 'Model 3']],
            ['Togg T10X V2 RWD 2024', 1250000, 'T10X V2, 8.500 km. Yerli uretim, garantili, hizli sarj.', ['year' => 2024, 'km' => 8500, 'fuel' => 'Elektrik', 'hp' => 218, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Kirmizi', 'make' => 'Togg', 'model' => 'T10X']],
            ['Mazda CX-5 2.0 SkyActiv-G 2020', 1125000, 'CX-5 Comfort, 61.000 km, benzin. Bose ses, deri.', ['year' => 2020, 'km' => 61000, 'fuel' => 'Benzin', 'engine_cc' => 1998, 'hp' => 165, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Kirmizi', 'make' => 'Mazda', 'model' => 'CX-5']],
            ['Jeep Compass 1.3 Turbo Limited 2021', 1180000, 'Compass Limited, 47.000 km. 4x4, Uconnect NAV.', ['year' => 2021, 'km' => 47000, 'fuel' => 'Benzin', 'engine_cc' => 1332, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Yesil', 'make' => 'Jeep', 'model' => 'Compass']],
            ['Land Rover Range Rover Evoque 2020', 2450000, 'Evoque R-Dynamic, 38.000 km. Meridian ses, Matrix LED.', ['year' => 2020, 'km' => 38000, 'fuel' => 'Dizel', 'engine_cc' => 1999, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Siyah', 'make' => 'Land Rover', 'model' => 'Range Rover']],
            ['Porsche Macan S 2019', 3250000, 'Macan S, 55.000 km, benzin. Sport Chrono, PDCC.', ['year' => 2019, 'km' => 55000, 'fuel' => 'Benzin', 'engine_cc' => 2995, 'hp' => 354, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Gri', 'make' => 'Porsche', 'model' => 'Macan']],
            ['Cupra Formentor 1.5 TSI 2022', 1350000, 'Formentor VZ-Line, 29.000 km. Full paket, adaptif far.', ['year' => 2022, 'km' => 29000, 'fuel' => 'Benzin', 'engine_cc' => 1498, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Mavi', 'make' => 'Cupra', 'model' => 'Formentor']],
            ['BYD Atto 3 Design 2024', 1185000, 'Atto 3 Design, 12.000 km. Blade batarya, garantili.', ['year' => 2024, 'km' => 12000, 'fuel' => 'Elektrik', 'hp' => 204, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Gri', 'make' => 'BYD', 'model' => 'Atto 3']],
            ['Alfa Romeo Tonale 1.5 Hybrid 2023', 1585000, 'Tonale Veloce, 15.000 km. Q4 AWD, sport paket.', ['year' => 2023, 'km' => 15000, 'fuel' => 'Hibrit', 'engine_cc' => 1469, 'hp' => 160, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Kirmizi', 'make' => 'Alfa Romeo', 'model' => 'Tonale']],
            ['Subaru Forester 2.0i Premium 2021', 1285000, 'Forester Premium, 42.000 km. Eyesight, X-Mode.', ['year' => 2021, 'km' => 42000, 'fuel' => 'Benzin', 'engine_cc' => 1995, 'hp' => 156, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Yesil', 'make' => 'Subaru', 'model' => 'Forester']],
            ['Lexus NX 350h Executive 2022', 2385000, 'NX 350h Executive, 26.000 km. Mark Levinson, hud.', ['year' => 2022, 'km' => 26000, 'fuel' => 'Hibrit', 'engine_cc' => 2487, 'hp' => 242, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Siyah', 'make' => 'Lexus', 'model' => 'NX']],
            ['Fiat Egea 1.6 Multijet Lounge 2019', 685000, 'Egea Lounge, 98.000 km, dizel. Sunroof, navigasyon.', ['year' => 2019, 'km' => 98000, 'fuel' => 'Dizel', 'engine_cc' => 1598, 'hp' => 120, 'transmission' => 'Manuel', 'body' => 'Sedan', 'color' => 'Beyaz', 'make' => 'Fiat', 'model' => 'Egea']],
            ['Honda Civic 1.5 Turbo Elegance 2022', 1285000, 'Civic Elegance, 33.000 km. Honda Sensing, LED.', ['year' => 2022, 'km' => 33000, 'fuel' => 'Benzin', 'engine_cc' => 1498, 'hp' => 182, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'color' => 'Gri', 'make' => 'Honda', 'model' => 'Civic']],
            ['Mitsubishi Outlander 2.0 MIVEC 2020', 985000, 'Outlander Intense, 67.000 km. 7 koltuk, 4WD.', ['year' => 2020, 'km' => 67000, 'fuel' => 'Benzin', 'engine_cc' => 1998, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Beyaz', 'make' => 'Mitsubishi', 'model' => 'Outlander']],
            ['Mini Cooper S 3 Kapı 2021', 1185000, 'Cooper S, 36.000 km. JCW paket, harman kardon.', ['year' => 2021, 'km' => 36000, 'fuel' => 'Benzin', 'engine_cc' => 1998, 'hp' => 192, 'transmission' => 'Otomatik', 'body' => 'Hatchback', 'doors' => 3, 'color' => 'Sari', 'make' => 'Mini', 'model' => 'Cooper']],
            ['Citroën C5 Aircross Shine 2021', 985000, 'C5 Aircross Shine, 54.000 km. Advanced Comfort, Grip Control.', ['year' => 2021, 'km' => 54000, 'fuel' => 'Dizel', 'engine_cc' => 1499, 'hp' => 130, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Mavi', 'make' => 'Citroën', 'model' => 'C5 Aircross']],
            ['Suzuki Vitara 1.4 Boosterjet 2020', 825000, 'Vitara GLX, 71.000 km. AllGrip, Apple CarPlay.', ['year' => 2020, 'km' => 71000, 'fuel' => 'Benzin', 'engine_cc' => 1373, 'hp' => 140, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Turuncu', 'make' => 'Suzuki', 'model' => 'Vitara']],
            ['Jaguar F-Pace 2.0 D R-Dynamic 2019', 1850000, 'F-Pace R-Dynamic, 62.000 km. Meridyen ses, panoramik.', ['year' => 2019, 'km' => 62000, 'fuel' => 'Dizel', 'engine_cc' => 1999, 'hp' => 180, 'transmission' => 'Otomatik', 'body' => 'SUV', 'color' => 'Siyah', 'make' => 'Jaguar', 'model' => 'F-Pace']],
        ];

        $out = [];
        foreach ($rows as $i => [$title, $price, $desc, $vehicle]) {
            $out[] = self::listing('Otomobil', 'otomobil', $title, $city($i), (float) $price, $desc, $vehicle, $photos, 'SALE', true);
        }

        return $out;
    }

    /** @param callable(int): string $city @return list<array<string,mixed>> */
    private static function motosikletDiverse(callable $city): array
    {
        $motoPhotos = [
            'https://images.unsplash.com/photo-1558981403-c5f9899a28bc?w=1200',
            'https://images.unsplash.com/photo-1568772585407-9361f9bf3a87?w=1200',
            'https://images.unsplash.com/photo-1449426468159-d96dbf50f910?w=1200',
        ];

        $rows = [
            ['Ducati Monster 937 2022', 485000, 'Monster 937, 6.200 km. Termignoni egzoz, quickshifter.', ['year' => 2022, 'km' => 6200, 'fuel' => 'Benzin', 'engine_cc' => 937, 'hp' => 111, 'transmission' => 'Manuel', 'moto_type' => 'Naked', 'color' => 'Kirmizi', 'make' => 'Ducati', 'model' => 'Monster']],
            ['KTM 390 Duke 2023', 265000, '390 Duke, 4.100 km. ABS, TFT ekran, garaj araci.', ['year' => 2023, 'km' => 4100, 'fuel' => 'Benzin', 'engine_cc' => 373, 'hp' => 44, 'transmission' => 'Manuel', 'moto_type' => 'Naked', 'make' => 'KTM', 'model' => '390 Duke']],
            ['Suzuki GSX-S750 2021', 425000, 'GSX-S750, 11.800 km. Sport naked, bakimli.', ['year' => 2021, 'km' => 11800, 'fuel' => 'Benzin', 'engine_cc' => 749, 'hp' => 114, 'transmission' => 'Manuel', 'moto_type' => 'Naked', 'color' => 'Mavi', 'make' => 'Suzuki', 'model' => 'GSX-S']],
            ['Harley-Davidson Sportster S 2022', 685000, 'Sportster S, 7.500 km. Revolution Max, keyless.', ['year' => 2022, 'km' => 7500, 'fuel' => 'Benzin', 'engine_cc' => 1252, 'hp' => 121, 'transmission' => 'Manuel', 'moto_type' => 'Cruiser', 'make' => 'Harley-Davidson', 'model' => 'Sportster']],
            ['Aprilia RS 660 2023', 565000, 'RS 660, 3.800 km. Supersport, cornering ABS.', ['year' => 2023, 'km' => 3800, 'fuel' => 'Benzin', 'engine_cc' => 659, 'hp' => 100, 'transmission' => 'Manuel', 'moto_type' => 'Supersport', 'color' => 'Siyah', 'make' => 'Aprilia', 'model' => 'RS']],
            ['Royal Enfield Classic 350 2022', 185000, 'Classic 350 Chrome, 9.200 km. Retro, az kullanilmis.', ['year' => 2022, 'km' => 9200, 'fuel' => 'Benzin', 'engine_cc' => 349, 'hp' => 20, 'transmission' => 'Manuel', 'moto_type' => 'Cruiser', 'color' => 'Siyah', 'make' => 'Royal Enfield', 'model' => 'Classic']],
            ['Triumph Tiger 900 Rally Pro 2021', 485000, 'Tiger 900 Rally Pro, 18.500 km. Adventure, cruise control.', ['year' => 2021, 'km' => 18500, 'fuel' => 'Benzin', 'engine_cc' => 888, 'hp' => 95, 'transmission' => 'Manuel', 'moto_type' => 'Enduro', 'make' => 'Triumph', 'model' => 'Tiger']],
            ['Vespa GTS 300 Super 2023', 195000, 'GTS 300 Super, 2.400 km. Scooter, smart key.', ['year' => 2023, 'km' => 2400, 'fuel' => 'Benzin', 'engine_cc' => 278, 'hp' => 24, 'transmission' => 'Otomatik', 'moto_type' => 'Scooter', 'color' => 'Beyaz', 'make' => 'Vespa', 'model' => 'GTS']],
            ['BMW R 1250 GS Adventure 2020', 685000, 'R 1250 GS Adventure, 32.000 km. Full paket, ESA.', ['year' => 2020, 'km' => 32000, 'fuel' => 'Benzin', 'engine_cc' => 1254, 'hp' => 136, 'transmission' => 'Manuel', 'moto_type' => 'Enduro', 'make' => 'BMW', 'model' => 'R 1250 GS']],
            ['Honda Africa Twin 1100 Adventure Sports 2022', 585000, 'Africa Twin AS, 14.600 km. DCT, Apple CarPlay.', ['year' => 2022, 'km' => 14600, 'fuel' => 'Benzin', 'engine_cc' => 1084, 'hp' => 102, 'transmission' => 'Otomatik', 'moto_type' => 'Enduro', 'color' => 'Kirmizi', 'make' => 'Honda', 'model' => 'Africa Twin']],
            ['Benelli TRK 502 X 2021', 285000, 'TRK 502 X, 21.000 km. Adventure tur, ucuz bakim.', ['year' => 2021, 'km' => 21000, 'fuel' => 'Benzin', 'engine_cc' => 500, 'hp' => 47, 'transmission' => 'Manuel', 'moto_type' => 'Enduro', 'make' => 'Benelli', 'model' => 'TRK']],
            ['Piaggio MP3 530 HPE Sport 2022', 325000, 'MP3 530, 8.900 km. Uc teker scooter, ABS.', ['year' => 2022, 'km' => 8900, 'fuel' => 'Benzin', 'engine_cc' => 493, 'hp' => 44, 'transmission' => 'Otomatik', 'moto_type' => 'Scooter', 'make' => 'Piaggio', 'model' => 'MP3']],
        ];

        $out = [];
        foreach ($rows as $i => [$title, $price, $desc, $vehicle]) {
            $out[] = self::listing('Motosiklet', 'motosiklet', $title, $city($i + 30), (float) $price, $desc, $vehicle, $motoPhotos, 'SALE', true);
        }

        return $out;
    }

    /** @param callable(int): string $city @return list<array<string,mixed>> */
    private static function bisikletDiverse(callable $city): array
    {
        $bikePhotos = [
            'https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=1200',
            'https://images.unsplash.com/photo-1485965120180-e83225084751?w=1200',
            'https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=1200',
        ];

        $rows = [
            ['Specialized Rockhopper Comp 29', 42000, 'Rockhopper Comp, 600 km. Hidrolik disk, 1x12.', ['year' => 2023, 'km' => 600, 'bike_type' => 'Dag', 'frame' => 'Aluminyum', 'wheel' => '29"', 'condition' => 'Ikinci el', 'color' => 'Siyah', 'make' => 'Specialized', 'model' => 'Rockhopper']],
            ['Cannondale Synapse Carbon 105', 78000, 'Synapse karbon, 1.200 km. Endurance yol bisikleti.', ['year' => 2021, 'km' => 1200, 'bike_type' => 'Yol', 'frame' => 'Karbon', 'wheel' => '700c', 'condition' => 'Ikinci el', 'color' => 'Yesil', 'make' => 'Cannondale', 'model' => 'Synapse']],
            ['Scott Scale 970 2022', 35000, 'Scale 970 hardtail, 900 km. XC kullanim.', ['year' => 2022, 'km' => 900, 'bike_type' => 'Dag', 'frame' => 'Aluminyum', 'wheel' => '29"', 'condition' => 'Ikinci el', 'make' => 'Scott', 'model' => 'Scale']],
            ['Merida Big Nine 300 2023', 28500, 'Big Nine 300, 450 km. Giris seviye 29er.', ['year' => 2023, 'km' => 450, 'bike_type' => 'Dag', 'frame' => 'Aluminyum', 'wheel' => '29"', 'condition' => 'Ikinci el', 'color' => 'Turuncu', 'make' => 'Merida', 'model' => 'Big Nine']],
            ['Canyon Neuron CF 7 2021', 95000, 'Neuron CF trail, 2.100 km. Karbon kadro, Fox sus.', ['year' => 2021, 'km' => 2100, 'bike_type' => 'Dag', 'frame' => 'Karbon', 'wheel' => '29"', 'condition' => 'Ikinci el', 'color' => 'Gri', 'make' => 'Canyon', 'model' => 'Neuron']],
            ['Decathlon Triban RC 520 Yol', 22000, 'Triban RC 520, 800 km. Shimano 105, disk fren.', ['year' => 2022, 'km' => 800, 'bike_type' => 'Yol', 'frame' => 'Aluminyum', 'wheel' => '700c', 'condition' => 'Ikinci el', 'make' => 'Decathlon', 'model' => 'Triban']],
        ];

        $out = [];
        foreach ($rows as $i => [$title, $price, $desc, $vehicle]) {
            $out[] = self::listing('Bisiklet', 'bisiklet', $title, $city($i + 42), (float) $price, $desc, $vehicle, $bikePhotos, 'TRADE', true);
        }

        return $out;
    }

    /** @param callable(int): string $city @return list<array<string,mixed>> */
    private static function ticariDiverse(callable $city): array
    {
        $comPhotos = [
            'https://images.unsplash.com/photo-1619642751034-765df33d5825?w=1200',
            'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=1200',
            'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200',
        ];

        $rows = [
            ['Peugeot Boxer 2.2 BlueHDi L3H2 2021', 785000, 'Peugeot Boxer panelvan, 72.000 km. Frigo uyumlu.', ['year' => 2021, 'km' => 72000, 'fuel' => 'Dizel', 'engine_cc' => 2179, 'hp' => 140, 'transmission' => 'Manuel', 'body' => 'Minivan', 'color' => 'Beyaz', 'make' => 'Peugeot', 'model' => 'Boxer', 'commercial_type' => 'kamyonet']],
            ['Renault Master L2H2 2.3 dCi 2020', 695000, 'Renault Master panelvan, 98.000 km. Raf sistemi.', ['year' => 2020, 'km' => 98000, 'fuel' => 'Dizel', 'engine_cc' => 2299, 'hp' => 135, 'transmission' => 'Manuel', 'body' => 'Minivan', 'make' => 'Renault', 'model' => 'Master', 'commercial_type' => 'kamyonet']],
            ['MAN TGS 18.440 4x2 2018', 2850000, 'MAN TGS kamyon, 412.000 km. Liftli kasa, bakimli.', ['year' => 2018, 'km' => 412000, 'fuel' => 'Dizel', 'engine_cc' => 10518, 'hp' => 440, 'transmission' => 'Manuel', 'body' => 'Kamyon', 'make' => 'MAN', 'model' => 'TGS', 'commercial_type' => 'kamyon']],
            ['Iveco Daily 35S14 Tarim 2019', 685000, 'Iveco Daily tarim/lojistik, 156.000 km.', ['year' => 2019, 'km' => 156000, 'fuel' => 'Dizel', 'engine_cc' => 2287, 'hp' => 136, 'transmission' => 'Manuel', 'body' => 'Pick-up', 'make' => 'Iveco', 'model' => 'Daily', 'commercial_type' => 'tarim']],
            ['Scania R 450 Highline 2019', 4250000, 'Scania R450 cekici, 680.000 km. Retarder, klima.', ['year' => 2019, 'km' => 680000, 'fuel' => 'Dizel', 'engine_cc' => 12742, 'hp' => 450, 'transmission' => 'Otomatik', 'body' => 'Cekici', 'make' => 'Scania', 'model' => 'R-Series', 'commercial_type' => 'cekici']],
            ['Volvo FH 460 Globetrotter 2020', 3950000, 'Volvo FH cekici + dorse set, 520.000 km.', ['year' => 2020, 'km' => 520000, 'fuel' => 'Dizel', 'engine_cc' => 12777, 'hp' => 460, 'transmission' => 'Otomatik', 'make' => 'Volvo', 'model' => 'FH', 'commercial_type' => 'dorse']],
            ['Mercedes-Benz Sprinter Minibus 2018', 985000, 'Sprinter 16+1 minibus, 245.000 km. Otobus ruhsatli.', ['year' => 2018, 'km' => 245000, 'fuel' => 'Dizel', 'engine_cc' => 2143, 'hp' => 163, 'transmission' => 'Manuel', 'body' => 'Minivan', 'make' => 'Mercedes-Benz', 'model' => 'Sprinter', 'commercial_type' => 'otobus']],
            ['MAN TGE 3140 Forklift Uyumlu 2021', 585000, 'MAN TGE yuksek tavan, 45.000 km. Depo ic lojistik.', ['year' => 2021, 'km' => 45000, 'fuel' => 'Dizel', 'engine_cc' => 1968, 'hp' => 140, 'transmission' => 'Manuel', 'make' => 'MAN', 'model' => 'TGE', 'commercial_type' => 'forklift']],
            ['Fiat Doblo 1.6 Multijet Taksi 2019', 485000, 'Doblo taksi, 198.000 km. Ruhsatli, LPG.', ['year' => 2019, 'km' => 198000, 'fuel' => 'Dizel', 'engine_cc' => 1598, 'hp' => 105, 'transmission' => 'Manuel', 'body' => 'Minivan', 'color' => 'Sari', 'make' => 'Fiat', 'model' => 'Doblo', 'commercial_type' => 'taksi']],
            ['Iveco Eurocargo 120E22 Is Makinesi Tasiyici 2017', 1650000, 'Eurocargo kamyon, vinç aparatli, 298.000 km.', ['year' => 2017, 'km' => 298000, 'fuel' => 'Dizel', 'engine_cc' => 5880, 'hp' => 220, 'transmission' => 'Manuel', 'make' => 'Iveco', 'model' => 'Eurocargo', 'commercial_type' => 'is-makinesi']],
            ['Renault Trafic Romork Cekici 2020', 625000, 'Trafic romork cekici uyumlu, 112.000 km.', ['year' => 2020, 'km' => 112000, 'fuel' => 'Dizel', 'engine_cc' => 1997, 'hp' => 120, 'transmission' => 'Manuel', 'make' => 'Renault', 'model' => 'Trafic', 'commercial_type' => 'romork']],
        ];

        $out = [];
        foreach ($rows as $i => [$title, $price, $desc, $vehicle]) {
            $out[] = self::listing('Ticari Arac', 'ticari', $title, $city($i + 48), (float) $price, $desc, $vehicle, $comPhotos, 'SALE', true);
        }

        return $out;
    }

    /** @param callable(int): string $city @return list<array<string,mixed>> */
    private static function antikaDiverse(callable $city): array
    {
        $antPhotos = [
            'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200',
            'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1200',
            'https://images.unsplash.com/photo-1584345604480-4d6a5a166962?w=1200',
        ];

        $rows = [
            ['1961 Jaguar E-Type Series 1', 5200000, 'E-Type 3.8, restorasyonlu. Matching numbers.', ['year' => 1961, 'km' => 62000, 'fuel' => 'Benzin', 'engine_cc' => 3781, 'hp' => 265, 'transmission' => 'Manuel', 'body' => 'Coupe', 'era' => '1950-1970', 'condition' => 'Restorasyonlu', 'color' => 'Yesil', 'make' => 'Jaguar', 'model' => 'E-Type']],
            ['1974 BMW 2002 tii', 1850000, '2002 tii, orijinal motor. Koleksiyoner araci.', ['year' => 1974, 'km' => 98000, 'fuel' => 'Benzin', 'engine_cc' => 1990, 'hp' => 130, 'transmission' => 'Manuel', 'body' => 'Sedan', 'era' => '1970-1990', 'condition' => 'Orijinal', 'color' => 'Mavi', 'make' => 'BMW', 'model' => '2002']],
            ['1969 Chevrolet Corvette C3 Stingray', 3850000, 'Corvette C3, 350ci V8. Proje/restorasyon.', ['year' => 1969, 'km' => 72000, 'fuel' => 'Benzin', 'engine_cc' => 5733, 'hp' => 300, 'transmission' => 'Manuel', 'body' => 'Coupe', 'era' => '1950-1970', 'condition' => 'Proje araci', 'color' => 'Sari', 'make' => 'Chevrolet', 'model' => 'Corvette']],
            ['1982 Fiat 124 Spider Pininfarina', 750000, '124 Spider, 68.000 km. Ust acilir, bakimli.', ['year' => 1982, 'km' => 68000, 'fuel' => 'Benzin', 'engine_cc' => 1995, 'hp' => 102, 'transmission' => 'Manuel', 'body' => 'Cabrio', 'era' => '1970-1990', 'condition' => 'Orijinal', 'color' => 'Kirmizi', 'make' => 'Fiat', 'model' => '124 Spider']],
            ['1978 Rolls Royce Silver Shadow II', 6500000, 'Silver Shadow II, chauffeur bakimli. Tam orijinal ic.', ['year' => 1978, 'km' => 112000, 'fuel' => 'Benzin', 'engine_cc' => 6750, 'hp' => 189, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'era' => '1970-1990', 'condition' => 'Restorasyonlu', 'color' => 'Siyah', 'make' => 'Rolls Royce', 'model' => 'Silver Shadow']],
        ];

        $out = [];
        foreach ($rows as $i => [$title, $price, $desc, $vehicle]) {
            $out[] = self::listing('Antika Arac', 'antika-arac', $title, $city($i + 59), (float) $price, $desc, $vehicle, $antPhotos, 'SALE', true);
        }

        return $out;
    }

    /**
     * @param list<string> $photos
     * @param array<string,mixed> $vehicle
     * @return array<string,mixed>
     */
    private static function listing(
        string $subcategory,
        string $segment,
        string $title,
        string $location,
        float $price,
        string $description,
        array $vehicle,
        array $photos,
        string $mode = 'SALE',
        bool $negotiable = true
    ): array {
        return [
            'title' => $title,
            'subcategory' => $subcategory,
            'location' => $location,
            'price' => $price,
            'description' => $description,
            'mode' => $mode,
            'negotiable' => $negotiable,
            'wanted' => $mode === 'TRADE' ? 'Benzer segment urun veya nakit takas' : '',
            'photos' => $photos,
            'attrs' => [
                'segment' => $segment,
                'vehicle' => $vehicle,
                'seller' => [
                    'type' => match ($segment) {
                        'motosiklet', 'ticari' => 'Galeri',
                        'bisiklet' => 'Magaza',
                        'antika-arac' => 'Sahibinden',
                        default => random_int(0, 1) ? 'Galeri' : 'Sahibinden',
                    },
                    'phone' => '+90 5' . random_int(30, 59) . ' ' . random_int(100, 999) . ' ' . random_int(10, 99) . ' ' . random_int(10, 99),
                ],
                'equipment' => self::equipmentFor($segment),
            ],
        ];
    }

    /** @return list<string> */
    private static function equipmentFor(string $segment): array
    {
        return match ($segment) {
            'motosiklet' => ['ABS', 'Alarm', 'Koruma barlari'],
            'bisiklet' => ['Disk fren', 'Hizli cikarma sele'],
            'ticari' => ['Klima', 'Raf sistemi', 'Geri vites kamerasi'],
            'antika-arac' => ['Orijinal anahtar', 'Servis defteri'],
            default => ['ABS', 'ESP', 'Klima', 'Park sensoru', 'Bluetooth'],
        };
    }
}
