<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Auth;
use App\Helpers\Database;

final class DemoSeedService
{
    public static function seed(): array
    {
        $pdo = Database::pdo();
        $messages = [];
        $now = microtime(true);

        $stmt = $pdo->prepare('SELECT id FROM users WHERE username = ? LIMIT 1');
        $stmt->execute(['demo']);
        $demo = $stmt->fetch();
        if (!$demo) {
            $pdo->prepare(
                'INSERT INTO users (username, password_hash, role, email, change_score, created_at)
                 VALUES (?,?,?,?,?,?)'
            )->execute(['demo', Auth::hashPassword('demo123456'), 'user', 'demo@changex.local', 72, $now]);
            $demoId = (int) $pdo->lastInsertId();
            $messages[] = 'demo / demo123456 kullanicisi olusturuldu';
        } else {
            $demoId = (int) $demo['id'];
            $messages[] = 'demo kullanicisi zaten var';
        }

        $listings = [
            [
                'BMW X2 2022 xDRIVE 25e',
                'BMW X2 xDrive25e, hibrit SUV. Servis bakimli, tek elden. CarPlay, deri koltuk, park sensoru.',
                'Araçlar', 'Otomobil', 'Istanbul', '',
                'SALE', 1450000.00,
                '["https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800","https://images.unsplash.com/photo-1617531653332-bd46c24f2068?w=800"]',
                json_encode([
                    'segment' => 'otomobil',
                    'vehicle' => [
                        'year' => 2022,
                        'km' => 45200,
                        'fuel' => 'Hibrit',
                        'engine_cc' => 1499,
                        'hp' => 220,
                        'doors' => 5,
                        'transmission' => 'Otomatik',
                        'body' => 'SUV',
                        'drive' => '4x4',
                        'color' => 'Gri',
                    ],
                    'seller' => ['type' => 'Yetkili galeri'],
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                'Yamaha MT-07 2021',
                '7.800 km, garaj bakimli naked motosiklet. ABS, quickshifter, aksesuar seti.',
                'Araçlar', 'Motosiklet', 'Ankara', 'Sport touring veya scooter',
                'SALE', 385000.00,
                '["https://images.unsplash.com/photo-1558981403-c5f9899a28bc?w=800"]',
                json_encode([
                    'segment' => 'motosiklet',
                    'vehicle' => [
                        'year' => 2021,
                        'km' => 7800,
                        'fuel' => 'Benzin',
                        'engine_cc' => 689,
                        'hp' => 73,
                        'transmission' => 'Manuel',
                        'moto_type' => 'Naked',
                        'color' => 'Siyah',
                    ],
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                'Decathlon Rockrider ST530',
                '27.5 jant dag bisikleti. Yeni zincir, bakimli, hafif aliminyum kadro.',
                'Araçlar', 'Bisiklet', 'Adana', 'Elektrikli scooter veya e-bike',
                'TRADE', null,
                '["https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=800"]',
                json_encode([
                    'segment' => 'bisiklet',
                    'vehicle' => [
                        'year' => 2022,
                        'km' => 1200,
                        'bike_type' => 'Dağ',
                        'frame' => 'Alüminyum',
                        'wheel' => '27.5"',
                        'condition' => 'İkinci el',
                        'color' => 'Turuncu',
                    ],
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                'Ford Transit Custom 2020',
                'Panelvan, 95.000 km, dizel, L2 uzun sasi. Servis bakimli ticari arac.',
                'Araçlar', 'Ticari Araç', 'Izmir', '',
                'SALE', 920000.00,
                '["https://images.unsplash.com/photo-1619642751034-765df33d5825?w=800"]',
                json_encode([
                    'segment' => 'ticari',
                    'vehicle' => [
                        'year' => 2020,
                        'km' => 95000,
                        'fuel' => 'Dizel',
                        'engine_cc' => 1995,
                        'hp' => 130,
                        'transmission' => 'Manuel',
                        'body' => 'Minivan',
                        'color' => 'Beyaz',
                    ],
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                '1967 Mercedes-Benz W108 280S',
                'Klasik sedan, restorasyonlu, orijinal motor. Koleksiyoner araci.',
                'Araçlar', 'Antika Araç', 'Istanbul', '',
                'SALE', 2850000.00,
                '["https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=800"]',
                json_encode([
                    'segment' => 'antika-arac',
                    'vehicle' => [
                        'year' => 1967,
                        'km' => 142000,
                        'fuel' => 'Benzin',
                        'engine_cc' => 2778,
                        'hp' => 140,
                        'transmission' => 'Manuel',
                        'body' => 'Sedan',
                        'era' => '1950–1970',
                        'condition' => 'Restorasyonlu',
                        'color' => 'Gümüş',
                    ],
                ], JSON_UNESCAPED_UNICODE),
            ],
        ];

        $hasAttrs = false;
        try {
            $cols = $pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();
            $hasAttrs = (bool) $cols;
        } catch (\Throwable) {
            $hasAttrs = false;
        }

        $insertSql = $hasAttrs
            ? 'INSERT INTO trade_listings (
              owner_id, title, description, category, subcategory, location, accept_categories, wanted_items,
              photo_urls, attrs_json, status, listing_mode, price_tl, mandal_units, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            : 'INSERT INTO trade_listings (
              owner_id, title, description, category, subcategory, location, accept_categories, wanted_items,
              photo_urls, status, listing_mode, price_tl, mandal_units, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)';
        $insert = $pdo->prepare($insertSql);

        $added = 0;
        foreach ($listings as $i => $L) {
            $chk = $pdo->prepare('SELECT id FROM trade_listings WHERE title = ? LIMIT 1');
            $chk->execute([$L[0]]);
            if ($chk->fetch()) {
                continue;
            }
            $insert->execute([
                $demoId,
                $L[0],
                $L[1],
                $L[2],
                $L[3],
                $L[4],
                '[]',
                $L[5],
                $L[8],
                ...($hasAttrs ? [$L[9] ?? null] : []),
                'APPROVED',
                $L[6],
                $L[7],
                10 + $i * 5,
                $now - (86400 * (6 - $i)),
                $now - ($i * 3600),
            ]);
            $added++;
        }
        $messages[] = $added . ' ornek ilan eklendi';
        return $messages;
    }
}
