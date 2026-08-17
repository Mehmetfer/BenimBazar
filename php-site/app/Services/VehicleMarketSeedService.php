<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Auth;
use App\Helpers\Database;

/**
 * Car.gr tarzı 5 kategori × 5 ilan + 5 test kullanıcı (rastgele sifre, kurulum ciktisinda).
 */
final class VehicleMarketSeedService
{
    private static function seedPassword(): string
    {
        return bin2hex(random_bytes(8));
    }

    private const LISTING_NO_BASE = 1000000000;

    /** @return list<string> */
    public static function seed(): array
    {
        $pdo = Database::pdo();
        $messages = [];
        $now = microtime(true);
        $seedPass = self::seedPassword();
        $hash = Auth::hashPassword($seedPass);
        $messages[] = 'Test kullanicilari sifresi (tek seferlik): ' . $seedPass;

        $users = [
            ['username' => 'araba_ahmet', 'email' => 'ahmet.yilmaz@changex.test', 'city' => 'Istanbul', 'phone' => '+90 532 111 2233'],
            ['username' => 'motor_selin', 'email' => 'selin.kaya@changex.test', 'city' => 'Ankara', 'phone' => '+90 533 444 5566'],
            ['username' => 'bisiklet_emre', 'email' => 'emre.demir@changex.test', 'city' => 'Izmir', 'phone' => '+90 534 777 8899'],
            ['username' => 'ticari_burak', 'email' => 'burak.celik@changex.test', 'city' => 'Bursa', 'phone' => '+90 535 222 3344'],
            ['username' => 'antika_deniz', 'email' => 'deniz.arslan@changex.test', 'city' => 'Antalya', 'phone' => '+90 536 555 6677'],
        ];

        $userIds = [];
        foreach ($users as $u) {
            $stmt = $pdo->prepare('SELECT id FROM users WHERE username = ? LIMIT 1');
            $stmt->execute([$u['username']]);
            $row = $stmt->fetch();
            if ($row) {
                $uid = (int) $row['id'];
                $pdo->prepare('UPDATE users SET password_hash = ?, email = ? WHERE id = ?')
                    ->execute([$hash, $u['email'], $uid]);
                $messages[] = 'Kullanici guncellendi: ' . $u['username'];
            } else {
                $pdo->prepare(
                    'INSERT INTO users (username, password_hash, role, email, change_score, created_at)
                     VALUES (?,?,?,?,?,?)'
                )->execute([$u['username'], $hash, 'user', $u['email'], random_int(55, 92), $now - random_int(1000, 90000)]);
                $uid = (int) $pdo->lastInsertId();
                $messages[] = 'Kullanici olusturuldu: ' . $u['username'];
            }
            $userIds[$u['username']] = $uid;
        }

        $catalog = self::catalog();
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
        $added = 0;
        $listingNos = [];

        foreach ($catalog as $i => $item) {
            $chk = $pdo->prepare('SELECT id FROM trade_listings WHERE title = ? LIMIT 1');
            $chk->execute([$item['title']]);
            if ($chk->fetch()) {
                $messages[] = 'Atlandi (var): ' . $item['title'];
                continue;
            }

            $ownerId = $userIds[$item['owner']] ?? reset($userIds);
            $photos = json_encode($item['photos'], JSON_UNESCAPED_UNICODE);
            $attrs = json_encode($item['attrs'], JSON_UNESCAPED_UNICODE);
            $created = $now - (86400 * random_int(1, 45)) - random_int(0, 86400);

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
                10 + ($i % 8) * 3,
                $created,
                $created + random_int(3600, 72000),
            ];

            $insert->execute($params);
            $id = (int) $pdo->lastInsertId();
            $no = self::LISTING_NO_BASE + $id;
            $listingNos[] = $no . ' — ' . $item['subcategory'] . ': ' . $item['title'];
            $added++;
        }

        $messages[] = $added . ' yeni arac ilani eklendi (toplam hedef: 25)';
        $messages[] = '--- Ilan numaralari ---';
        foreach ($listingNos as $line) {
            $messages[] = $line;
        }

        return $messages;
    }

    /** @return list<array<string,mixed>> */
    private static function catalog(): array
    {
        $u = static fn (string $key): string => $key;

        return array_merge(
            self::otomobilPack($u),
            self::motosikletPack($u),
            self::bisikletPack($u),
            self::ticariPack($u),
            self::antikaPack($u),
        );
    }

    /** @return list<array<string,mixed>> */
    private static function otomobilPack(callable $u): array
    {
        return [
            self::car($u('araba_ahmet'), 'BMW 320i M Sport 2019', 'Istanbul', 1185000, 'BMW 320i M Sport, 68.000 km, benzin, otomatik. Servis bakimli, hatasiz boya.', 'otomobil', ['year' => 2019, 'km' => 68000, 'fuel' => 'Benzin', 'engine_cc' => 1998, 'hp' => 184, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'drive' => 'Arkadan', 'color' => 'Gri', 'make' => 'BMW', 'model' => '320i'], ['https://images.unsplash.com/photo-1555215695-3004980ad54e?w=1200', 'https://images.unsplash.com/photo-1617531653332-bd46c24f2068?w=1200', 'https://images.unsplash.com/photo-1494976388531-d1058498bf69?w=1200']),
            self::car($u('araba_ahmet'), 'Mercedes-Benz C200 AMG 2020', 'Ankara', 1420000, 'C200 AMG Line, 52.000 km, hibrit assist. Cam tavan, deri, adaptif cruise.', 'otomobil', ['year' => 2020, 'km' => 52000, 'fuel' => 'Benzin', 'engine_cc' => 1497, 'hp' => 184, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'color' => 'Siyah', 'make' => 'Mercedes-Benz', 'model' => 'C200'], ['https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=1200', 'https://images.unsplash.com/photo-1617788138017-80ad40651399?w=1200', 'https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=1200']),
            self::car($u('araba_ahmet'), 'Volkswagen Golf 1.5 TSI 2021', 'Izmir', 985000, 'Golf Highline, 41.000 km, benzin, DSG. Apple CarPlay, LED far.', 'otomobil', ['year' => 2021, 'km' => 41000, 'fuel' => 'Benzin', 'engine_cc' => 1498, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'Hatchback', 'doors' => 5, 'color' => 'Beyaz', 'make' => 'Volkswagen', 'model' => 'Golf'], ['https://images.unsplash.com/photo-1542362567-b07e54358753?w=1200', 'https://images.unsplash.com/photo-1583121274602-3e2820c69888?w=1200', 'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=1200']),
            self::car($u('araba_ahmet'), 'Toyota Corolla 1.6 Vision 2018', 'Bursa', 765000, 'Corolla Vision, 112.000 km, benzin, manuel. Bakimli aile araci.', 'otomobil', ['year' => 2018, 'km' => 112000, 'fuel' => 'Benzin', 'engine_cc' => 1598, 'hp' => 132, 'transmission' => 'Manuel', 'body' => 'Sedan', 'color' => 'Gümüş', 'make' => 'Toyota', 'model' => 'Corolla'], ['https://images.unsplash.com/photo-1621007947382-bef3d5b4e089?w=1200', 'https://images.unsplash.com/photo-1609521263047-f8f205293bb4?w=1200', 'https://images.unsplash.com/photo-1549399542-7e3f8b79c341?w=1200']),
            self::car($u('araba_ahmet'), 'Audi A3 Sportback 35 TFSI 2022', 'Antalya', 1350000, 'A3 Sportback Advanced, 28.000 km. Virtual cockpit, park paketi.', 'otomobil', ['year' => 2022, 'km' => 28000, 'fuel' => 'Benzin', 'engine_cc' => 1498, 'hp' => 150, 'transmission' => 'Otomatik', 'body' => 'Hatchback', 'color' => 'Mavi', 'make' => 'Audi', 'model' => 'A3'], ['https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=1200', 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1200', 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200']),
        ];
    }

    /** @return list<array<string,mixed>> */
    private static function motosikletPack(callable $u): array
    {
        return [
            self::moto($u('motor_selin'), 'Yamaha MT-07 ABS 2021', 'Istanbul', 385000, 'MT-07 ABS, 8.200 km, naked. Quickshifter, korumalar.', ['year' => 2021, 'km' => 8200, 'fuel' => 'Benzin', 'engine_cc' => 689, 'hp' => 73, 'transmission' => 'Manuel', 'moto_type' => 'Naked', 'color' => 'Siyah', 'make' => 'Yamaha', 'model' => 'MT-07'], ['https://images.unsplash.com/photo-1558981403-c5f9899a28bc?w=1200', 'https://images.unsplash.com/photo-1449426468159-d96dbf50f910?w=1200', 'https://images.unsplash.com/photo-1568772585407-9361f9bf3a87?w=1200']),
            self::moto($u('motor_selin'), 'Honda CB650R 2022', 'Ankara', 465000, 'CB650R, 5.600 km, neo retro naked. Akrapovic egzoz.', ['year' => 2022, 'km' => 5600, 'fuel' => 'Benzin', 'engine_cc' => 649, 'hp' => 95, 'transmission' => 'Manuel', 'moto_type' => 'Naked', 'make' => 'Honda', 'model' => 'CB650R'], ['https://images.unsplash.com/photo-1609630875171-bf047106d418?w=1200', 'https://images.unsplash.com/photo-1558618048-3c8c76ca7d13?w=1200', 'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=1200']),
            self::moto($u('motor_selin'), 'Kawasaki Ninja 650 2020', 'Izmir', 395000, 'Ninja 650, 14.300 km, supersport tur. ABS, slider set.', ['year' => 2020, 'km' => 14300, 'fuel' => 'Benzin', 'engine_cc' => 649, 'hp' => 68, 'transmission' => 'Manuel', 'moto_type' => 'Supersport', 'color' => 'Yeşil', 'make' => 'Kawasaki', 'model' => 'Ninja 650'], ['https://images.unsplash.com/photo-1568772585407-9361f9bf3a87?w=1200', 'https://images.unsplash.com/photo-1449426468159-d96dbf50f910?w=1200', 'https://images.unsplash.com/photo-1558981403-c5f9899a28bc?w=1200']),
            self::moto($u('motor_selin'), 'BMW G 310 R 2023', 'Bursa', 295000, 'G 310 R, 3.100 km, sehir icin ideal. Garaj araci.', ['year' => 2023, 'km' => 3100, 'fuel' => 'Benzin', 'engine_cc' => 313, 'hp' => 34, 'transmission' => 'Manuel', 'moto_type' => 'Naked', 'make' => 'BMW', 'model' => 'G 310 R'], ['https://images.unsplash.com/photo-1558980664-769d51dfa7a2?w=1200', 'https://images.unsplash.com/photo-1609630875171-bf047106d418?w=1200', 'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=1200']),
            self::moto($u('motor_selin'), 'Yamaha XMAX 300 Tech MAX 2022', 'Antalya', 245000, 'XMAX 300 Tech MAX scooter, 9.800 km. Smart key, TFT ekran.', ['year' => 2022, 'km' => 9800, 'fuel' => 'Benzin', 'engine_cc' => 292, 'hp' => 28, 'transmission' => 'Otomatik', 'moto_type' => 'Scooter', 'color' => 'Gri', 'make' => 'Yamaha', 'model' => 'XMAX 300'], ['https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200', 'https://images.unsplash.com/photo-1558981403-c5f9899a28bc?w=1200', 'https://images.unsplash.com/photo-1568772585407-9361f9bf3a87?w=1200']),
        ];
    }

    /** @return list<array<string,mixed>> */
    private static function bisikletPack(callable $u): array
    {
        return [
            self::bike($u('bisiklet_emre'), 'Decathlon Rockrider ST530 27.5', 'Istanbul', 18500, 'Dag bisikleti, aliminyum kadro, 1.200 km kullanim. Yeni zincir.', ['year' => 2022, 'km' => 1200, 'bike_type' => 'Dağ', 'frame' => 'Alüminyum', 'wheel' => '27.5"', 'condition' => 'İkinci el', 'color' => 'Turuncu', 'make' => 'Decathlon', 'model' => 'Rockrider'], ['https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=1200', 'https://images.unsplash.com/photo-1485965120180-e83225084751?w=1200', 'https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=1200']),
            self::bike($u('bisiklet_emre'), 'Trek Marlin 7 29 Jant', 'Ankara', 42000, 'Trek Marlin 7, 800 km. Hidrolik disk fren, 1x12 Shimano.', ['year' => 2023, 'km' => 800, 'bike_type' => 'Dağ', 'frame' => 'Alüminyum', 'wheel' => '29"', 'condition' => 'İkinci el', 'color' => 'Mavi', 'make' => 'Trek', 'model' => 'Marlin'], ['https://images.unsplash.com/photo-1485965120180-e83225084751?w=1200', 'https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=1200', 'https://images.unsplash.com/photo-1511994298241-608e28f14fde?w=1200']),
            self::bike($u('bisiklet_emre'), 'Giant Talon 2 2021', 'Izmir', 28000, 'Giant Talon 2, sehir/dag hybrid. Bakimli, az kullanilmis.', ['year' => 2021, 'km' => 650, 'bike_type' => 'Dağ', 'frame' => 'Alüminyum', 'wheel' => '27.5"', 'condition' => 'İkinci el', 'color' => 'Siyah', 'make' => 'Giant', 'model' => 'Talon'], ['https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=1200', 'https://images.unsplash.com/photo-1571068316344-75bc76f77890?w=1200', 'https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=1200']),
            self::bike($u('bisiklet_emre'), 'Bianchi Sprint 105 Yol Bisikleti', 'Bursa', 95000, 'Bianchi Sprint karbon kadro, Shimano 105. 2.400 km.', ['year' => 2020, 'km' => 2400, 'bike_type' => 'Yol', 'frame' => 'Karbon', 'wheel' => '700c', 'condition' => 'İkinci el', 'color' => 'Mavi', 'make' => 'Bianchi', 'model' => 'Sprint'], ['https://images.unsplash.com/photo-1511994298241-608e28f14fde?w=1200', 'https://images.unsplash.com/photo-1485965120180-e83225084751?w=1200', 'https://images.unsplash.com/photo-1571068316344-75bc76f77890?w=1200']),
            self::bike($u('bisiklet_emre'), 'Cube Reaction Pro Elektrikli MTB', 'Antalya', 78000, 'Cube Reaction Hybrid Pro, 500Wh batarya. 1.900 km.', ['year' => 2022, 'km' => 1900, 'bike_type' => 'Elektrikli', 'frame' => 'Alüminyum', 'wheel' => '29"', 'condition' => 'İkinci el', 'color' => 'Gri', 'make' => 'Cube', 'model' => 'Reaction'], ['https://images.unsplash.com/photo-1571068316344-75bc76f77890?w=1200', 'https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=1200', 'https://images.unsplash.com/photo-1485965120180-e83225084751?w=1200']),
        ];
    }

    /** @return list<array<string,mixed>> */
    private static function ticariPack(callable $u): array
    {
        return [
            self::commercial($u('ticari_burak'), 'Ford Transit Custom 320 L2H1 2020', 'Istanbul', 920000, 'Ford Transit panelvan, 95.000 km, dizel, manuel. Servis bakimli.', ['year' => 2020, 'km' => 95000, 'fuel' => 'Dizel', 'engine_cc' => 1995, 'hp' => 130, 'transmission' => 'Manuel', 'body' => 'Minivan', 'color' => 'Beyaz', 'make' => 'Ford', 'model' => 'Transit Custom', 'commercial_type' => 'kamyonet'], ['https://images.unsplash.com/photo-1619642751034-765df33d5825?w=1200', 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=1200', 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200']),
            self::commercial($u('ticari_burak'), 'Mercedes-Benz Sprinter 316 CDI 2019', 'Ankara', 1150000, 'Sprinter 316 CDI, uzun sasi, 142.000 km. Klima, raf sistemi.', ['year' => 2019, 'km' => 142000, 'fuel' => 'Dizel', 'engine_cc' => 2143, 'hp' => 163, 'transmission' => 'Manuel', 'body' => 'Minivan', 'make' => 'Mercedes-Benz', 'model' => 'Sprinter', 'commercial_type' => 'kamyonet'], ['https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=1200', 'https://images.unsplash.com/photo-1619642751034-765df33d5825?w=1200', 'https://images.unsplash.com/photo-1519005060890-4a2962e1cc93?w=1200']),
            self::commercial($u('ticari_burak'), 'Fiat Ducato 2.3 Multijet 2021', 'Izmir', 875000, 'Fiat Ducato panelvan, 68.000 km. Frigo uyumlu kasa.', ['year' => 2021, 'km' => 68000, 'fuel' => 'Dizel', 'engine_cc' => 2287, 'hp' => 140, 'transmission' => 'Manuel', 'body' => 'Minivan', 'color' => 'Beyaz', 'make' => 'Fiat', 'model' => 'Ducato', 'commercial_type' => 'kamyonet'], ['https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200', 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=1200', 'https://images.unsplash.com/photo-1619642751034-765df33d5825?w=1200']),
            self::commercial($u('ticari_burak'), 'Volkswagen Crafter 35 2.0 TDI 2022', 'Bursa', 1280000, 'VW Crafter yuksek tavan, 41.000 km. Apple CarPlay, geri gorunus.', ['year' => 2022, 'km' => 41000, 'fuel' => 'Dizel', 'engine_cc' => 1968, 'hp' => 140, 'transmission' => 'Manuel', 'make' => 'Volkswagen', 'model' => 'Crafter', 'commercial_type' => 'kamyonet'], ['https://images.unsplash.com/photo-1519005060890-4a2962e1cc93?w=1200', 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200', 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=1200']),
            self::commercial($u('ticari_burak'), 'Isuzu N-Series NPR 2018 Kamyonet', 'Antalya', 685000, 'Isuzu NPR kamyonet, 178.000 km, dizel. Liftli kasa.', ['year' => 2018, 'km' => 178000, 'fuel' => 'Dizel', 'engine_cc' => 5193, 'hp' => 150, 'transmission' => 'Manuel', 'body' => 'Pick-up', 'make' => 'Isuzu', 'model' => 'N-Series', 'commercial_type' => 'kamyon'],
        ];
    }

    /** @return list<array<string,mixed>> */
    private static function antikaPack(callable $u): array
    {
        return [
            self::antique($u('antika_deniz'), '1967 Mercedes-Benz W108 280S', 'Istanbul', 2850000, 'Klasik Mercedes 280S, restorasyonlu, orijinal motor. Koleksiyoner araci.', ['year' => 1967, 'km' => 142000, 'fuel' => 'Benzin', 'engine_cc' => 2778, 'hp' => 140, 'transmission' => 'Manuel', 'body' => 'Sedan', 'era' => '1950–1970', 'condition' => 'Restorasyonlu', 'color' => 'Gümüş', 'make' => 'Mercedes-Benz', 'model' => '280S'], ['https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=1200', 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200', 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1200']),
            self::antique($u('antika_deniz'), '1965 Ford Mustang Fastback', 'Ankara', 3200000, 'Ford Mustang 1965 fastback, proje/restorasyonlu. V8 289.', ['year' => 1965, 'km' => 89000, 'fuel' => 'Benzin', 'engine_cc' => 4737, 'hp' => 225, 'transmission' => 'Manuel', 'body' => 'Coupe', 'era' => '1950–1970', 'condition' => 'Proje aracı', 'color' => 'Kırmızı', 'make' => 'Ford', 'model' => 'Mustang'], ['https://images.unsplash.com/photo-1584345604480-4d6a5a166962?w=1200', 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200', 'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=1200']),
            self::antique($u('antika_deniz'), '1972 Volkswagen Beetle 1300', 'Izmir', 650000, 'Vosvos 1300, orijinal gorunum. 96.000 km, bakimli.', ['year' => 1972, 'km' => 96000, 'fuel' => 'Benzin', 'engine_cc' => 1285, 'hp' => 44, 'transmission' => 'Manuel', 'body' => 'Hatchback', 'era' => '1970–1990', 'condition' => 'Orijinal', 'color' => 'Sarı', 'make' => 'Volkswagen', 'model' => 'Beetle'], ['https://images.unsplash.com/photo-1544636331-e26879cd4d9b?w=1200', 'https://images.unsplash.com/photo-1542362567-b07e54358753?w=1200', 'https://images.unsplash.com/photo-1583121274602-3e2820c69888?w=1200']),
            self::antique($u('antika_deniz'), '1959 Cadillac Series 62 Sedan', 'Bursa', 4100000, 'Cadillac 1959, Amerikan klasiği. Krom detay, orijinal ic mekan.', ['year' => 1959, 'km' => 78000, 'fuel' => 'Benzin', 'engine_cc' => 6200, 'hp' => 325, 'transmission' => 'Otomatik', 'body' => 'Sedan', 'era' => '1950 öncesi', 'condition' => 'Restorasyonlu', 'color' => 'Siyah', 'make' => 'Cadillac', 'model' => 'Series 62'], ['https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200', 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1200', 'https://images.unsplash.com/photo-1584345604480-4d6a5a166962?w=1200']),
            self::antique($u('antika_deniz'), '1985 Porsche 911 Carrera 3.2', 'Antalya', 5200000, 'Porsche 911 Carrera 3.2, 118.000 km. Matching numbers, servis gecmisi.', ['year' => 1985, 'km' => 118000, 'fuel' => 'Benzin', 'engine_cc' => 3164, 'hp' => 231, 'transmission' => 'Manuel', 'body' => 'Coupe', 'era' => '1970–1990', 'condition' => 'Orijinal', 'color' => 'Kırmızı', 'make' => 'Porsche', 'model' => '911 Carrera'], ['https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1200', 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200', 'https://images.unsplash.com/photo-1617788138017-80ad40651399?w=1200']),
        ];
    }

    /** @param list<string> $photos */
    /** @param array<string,mixed> $vehicle */
    private static function car(string $owner, string $title, string $location, float $price, string $desc, string $segment, array $vehicle, array $photos): array
    {
        return self::listing($owner, $title, 'Otomobil', $location, $price, $desc, $segment, $vehicle, $photos);
    }

    /** @param list<string> $photos */
    /** @param array<string,mixed> $vehicle */
    private static function moto(string $owner, string $title, string $location, float $price, string $desc, array $vehicle, array $photos): array
    {
        return self::listing($owner, $title, 'Motosiklet', $location, $price, $desc, 'motosiklet', $vehicle, $photos);
    }

    /** @param list<string> $photos */
    /** @param array<string,mixed> $vehicle */
    private static function bike(string $owner, string $title, string $location, float $price, string $desc, array $vehicle, array $photos): array
    {
        return self::listing($owner, $title, 'Bisiklet', $location, $price, $desc, 'bisiklet', $vehicle, $photos, 'TRADE', true);
    }

    /** @param list<string> $photos */
    /** @param array<string,mixed> $vehicle */
    private static function commercial(string $owner, string $title, string $location, float $price, string $desc, array $vehicle, array $photos): array
    {
        return self::listing($owner, $title, 'Ticari Araç', $location, $price, $desc, 'ticari', $vehicle, $photos);
    }

    /** @param list<string> $photos */
    /** @param array<string,mixed> $vehicle */
    private static function antique(string $owner, string $title, string $location, float $price, string $desc, array $vehicle, array $photos): array
    {
        return self::listing($owner, $title, 'Antika Araç', $location, $price, $desc, 'antika-arac', $vehicle, $photos);
    }

    /**
     * @param list<string> $photos
     * @param array<string,mixed> $vehicle
     * @return array<string,mixed>
     */
    private static function listing(
        string $owner,
        string $title,
        string $subcategory,
        string $location,
        float $price,
        string $description,
        string $segment,
        array $vehicle,
        array $photos,
        string $mode = 'SALE',
        bool $negotiable = true
    ): array {
        $sellers = [
            'araba_ahmet' => 'Sahibinden',
            'motor_selin' => 'Galeri',
            'bisiklet_emre' => 'Mağaza',
            'ticari_burak' => 'Galeri',
            'antika_deniz' => 'Sahibinden',
        ];
        $phones = [
            'araba_ahmet' => '+90 532 111 2233',
            'motor_selin' => '+90 533 444 5566',
            'bisiklet_emre' => '+90 534 777 8899',
            'ticari_burak' => '+90 535 222 3344',
            'antika_deniz' => '+90 536 555 6677',
        ];

        return [
            'owner' => $owner,
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
                    'type' => $sellers[$owner] ?? 'Sahibinden',
                    'phone' => $phones[$owner] ?? '',
                ],
                'equipment' => self::equipmentFor($segment),
            ],
        ];
    }

    /** @return list<string> */
    private static function equipmentFor(string $segment): array
    {
        return match ($segment) {
            'motosiklet' => ['ABS', 'Alarm', 'Kilitli zincir', 'Koruma barlari'],
            'bisiklet' => ['Disk fren', 'Hizli cikarma sele', 'Su matarasi'],
            'ticari' => ['Klima', 'Raf sistemi', 'Geri vites kamerasi'],
            'antika-arac' => ['Orijinal anahtar', 'Servis defteri', 'Yedek parca seti'],
            default => ['ABS', 'ESP', 'Klima', 'Park sensoru', 'Bluetooth'],
        };
    }
}
