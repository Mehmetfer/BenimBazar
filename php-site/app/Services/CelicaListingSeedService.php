<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;

/** Tek seferlik: 2005 Toyota Celica KKTC ilani (mockup verisi). */
final class CelicaListingSeedService
{
    public const TITLE = '2005 TOYOTA CELICA 1.8 BENZİNLİ – KIBRIS – SAĞ DÜMEN';

    /** @return array{ok:bool,messages:list<string>,listing_id?:int,listing_no?:int,url?:string} */
    public static function seed(?int $ownerId = null): array
    {
        $pdo = Database::pdo();
        $messages = [];
        $now = microtime(true);

        if ($ownerId === null || $ownerId <= 0) {
            $stmt = $pdo->prepare("SELECT id FROM users WHERE role = 'superadmin' ORDER BY id ASC LIMIT 1");
            $stmt->execute();
            $row = $stmt->fetch();
            if (!$row) {
                $stmt = $pdo->prepare('SELECT id FROM users ORDER BY id ASC LIMIT 1');
                $stmt->execute();
                $row = $stmt->fetch();
            }
            if (!$row) {
                return ['ok' => false, 'messages' => ['Kullanici bulunamadi.']];
            }
            $ownerId = (int) $row['id'];
        }

        $chk = $pdo->prepare('SELECT id FROM trade_listings WHERE title = ? LIMIT 1');
        $chk->execute([self::TITLE]);
        $existing = $chk->fetch();
        if ($existing) {
            $id = (int) $existing['id'];
            $base = (int) (cx_app_config()['listing_no_base'] ?? 1000000000);
            $no = $base + $id;
            (new ListingLifecycleService())->markPublished($id);

            return [
                'ok' => true,
                'messages' => ['Ilan zaten vardi; yayin tarihi guncellendi.'],
                'listing_id' => $id,
                'listing_no' => $no,
                'url' => '/listing.php?id=' . $id,
            ];
        }

        $photos = [
            'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=1600&q=85',
            'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1600&q=85',
            'https://images.unsplash.com/photo-1494976388531-d105849883bf?w=1600&q=85',
            'https://images.unsplash.com/photo-1544636331-e26879cd4d9b?w=1600&q=85',
        ];

        $attrs = [
            'segment' => 'otomobil',
            'vehicle' => [
                'year' => 2005,
                'km' => 178500,
                'fuel' => 'Benzin',
                'transmission' => 'Manuel',
                'engine_cc' => 1794,
                'hp' => 140,
                'body' => 'Coupe',
                'drive' => 'Önden',
                'color' => 'Kırmızı',
                'doors' => 2,
                'make' => 'Toyota',
                'model' => 'Celica',
                'engine' => '1.8',
                'steering' => 'Sağ (Kıbrıs)',
                'plate' => 'Kıbrıs Plakalı',
            ],
            'seller' => [
                'type' => 'Sahibinden',
                'phone' => '+90 533 123 45 67',
            ],
            'equipment' => [
                'Klima',
                'Elektrikli Camlar',
                'Merkezi Kilit',
                'Alüminyum Jantlar',
                'Spoiler',
                'Spor Koltuklar',
                'MP3 / AUX / USB',
                'Sis Farı',
            ],
        ];

        $description = '2005 model Toyota Celica 1.8 benzinli, Kıbrıs sağ direksiyon. '
            . 'Motor, şanzıman ve yürüyen aksamı sorunsuzdur. Düzenli bakımları yapılmıştır. '
            . 'İç ve dış kondisyonu gayet iyidir. Spor araba tutkunları için harika bir seçenek! '
            . 'Not: Aracın tüm belgeleri eksiksizdir.';

        $hasAttrs = (bool) $pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();

        $sql = $hasAttrs
            ? 'INSERT INTO trade_listings (
                owner_id, title, description, category, subcategory, `condition`, location,
                accept_categories, wanted_items, photo_urls, attrs_json, status, listing_mode,
                price_tl, price_negotiable, mandal_units, created_at, updated_at
              ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            : 'INSERT INTO trade_listings (
                owner_id, title, description, category, subcategory, `condition`, location,
                accept_categories, wanted_items, photo_urls, status, listing_mode,
                price_tl, price_negotiable, mandal_units, created_at, updated_at
              ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)';

        $params = [
            $ownerId,
            self::TITLE,
            $description,
            'Araçlar',
            'Otomobil',
            'good',
            'Lefkoşa, KKTC',
            '[]',
            '',
            json_encode($photos, JSON_UNESCAPED_UNICODE),
            ...($hasAttrs ? [json_encode($attrs, JSON_UNESCAPED_UNICODE)] : []),
            'APPROVED',
            'SALE',
            525000.00,
            1,
            0,
            $now,
            $now,
        ];

        $pdo->prepare($sql)->execute($params);
        $id = (int) $pdo->lastInsertId();
        (new ListingLifecycleService())->markPublished($id);

        $base = (int) (cx_app_config()['listing_no_base'] ?? 1000000000);
        $no = $base + $id;
        $messages[] = 'Toyota Celica ilani eklendi (superadmin owner_id=' . $ownerId . ').';
        $messages[] = 'Ilan no: ' . $no;

        return [
            'ok' => true,
            'messages' => $messages,
            'listing_id' => $id,
            'listing_no' => $no,
            'url' => '/listing.php?id=' . $id,
        ];
    }
}
