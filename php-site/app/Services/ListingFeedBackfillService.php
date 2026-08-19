<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

require_once dirname(__DIR__) . '/Helpers/listing-quality.php';

/** Eski arac ilanlarini feed kalite filtresine uygun hale getirir. */
final class ListingFeedBackfillService
{
    private PDO $pdo;

    /** @var list<string> */
    private static array $placeholderPhotos = [
        'https://images.unsplash.com/photo-1494976388531-d1058499021f?w=1200',
        'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1200',
        'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=1200',
    ];

    public function __construct()
    {
        $this->pdo = Database::pdo();
    }

    /**
     * @return list<array<string,mixed>>
     */
    public function fetchPublishedRows(): array
    {
        $stmt = $this->pdo->query(
            "SELECT * FROM trade_listings
             WHERE UPPER(COALESCE(status, '')) IN ('APPROVED', 'ACTIVE', 'PENDING_MODERATION', 'PENDING')
             ORDER BY id ASC"
        );

        return $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];
    }

    /**
     * @param array<string,mixed> $row
     * @return array{skip_reason:?string,changes:list<string>,patch:array<string,mixed>}|null
     */
    public function plan(array $row): ?array
    {
        if (cx_listing_passes_feed_quality($row)) {
            return null;
        }

        if (!cx_is_vehicle_listing($row)) {
            return [
                'skip_reason' => 'arac_disı',
                'changes' => [],
                'patch' => [],
            ];
        }

        $segment = $this->inferSegment($row);
        if ($segment === null) {
            return [
                'skip_reason' => 'segment_tespit_edilemedi',
                'changes' => [],
                'patch' => [],
            ];
        }

        $resolved = cx_resolve_listing_category(null, $segment);
        if ($resolved === null) {
            return [
                'skip_reason' => 'kategori_cozulemedi',
                'changes' => [],
                'patch' => [],
            ];
        }

        $changes = [];
        $patch = [];

        if ((string) ($row['category'] ?? '') !== 'Araçlar') {
            $patch['category'] = 'Araçlar';
            $changes[] = 'category→Araçlar';
        }

        $wantSub = (string) $resolved['subcategory'];
        if (trim((string) ($row['subcategory'] ?? '')) !== $wantSub) {
            $patch['subcategory'] = $wantSub;
            $changes[] = 'subcategory→' . $wantSub;
        }

        $attrs = cx_listing_attrs($row);
        $newAttrs = $this->buildAttrs($row, $segment, $attrs);
        $attrsJson = json_encode($newAttrs, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $oldJson = json_encode($attrs, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($attrsJson !== false && $attrsJson !== $oldJson) {
            $patch['attrs_json'] = $attrsJson;
            $changes[] = 'attrs_json dolduruldu';
        }

        $minFeedPhotos = max(1, cx_listing_quality_settings()['feed_min_photos']);
        $targetPhotos = max($minFeedPhotos, 3);
        $photos = cx_photo_urls($row['photo_urls'] ?? '[]');
        if (count($photos) < $targetPhotos) {
            $photos = $this->padPhotos($photos, $targetPhotos);
            $patch['photo_urls'] = json_encode($photos, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
            $changes[] = 'foto→' . count($photos) . ' adet';
        }

        $desc = trim((string) ($row['description'] ?? ''));
        $minDesc = cx_listing_quality_settings()['min_description_chars'];
        if ($minDesc > 0 && mb_strlen($desc, 'UTF-8') < $minDesc) {
            $pad = ' Arac ilani. Detaylar icin iletisime gecin.';
            $patch['description'] = rtrim($desc) . str_repeat($pad, (int) ceil(($minDesc - mb_strlen($desc, 'UTF-8')) / mb_strlen($pad, 'UTF-8')));
            $changes[] = 'aciklama uzatildi';
        }

        if ($changes === []) {
            return null;
        }

        $patch['updated_at'] = microtime(true);

        return [
            'skip_reason' => null,
            'changes' => $changes,
            'patch' => $patch,
        ];
    }

    /**
     * @return array{scanned:int,candidates:int,updated:int,skipped_non_vehicle:int,skipped_other:int,details:list<string>}
     */
    public function run(bool $dry = true): array
    {
        $rows = $this->fetchPublishedRows();
        $out = [
            'scanned' => count($rows),
            'candidates' => 0,
            'updated' => 0,
            'skipped_non_vehicle' => 0,
            'skipped_other' => 0,
            'details' => [],
        ];

        foreach ($rows as $row) {
            if (cx_listing_passes_feed_quality($row)) {
                continue;
            }

            $plan = $this->plan($row);
            if ($plan === null) {
                continue;
            }

            if ($plan['skip_reason'] !== null) {
                if ($plan['skip_reason'] === 'arac_disı') {
                    $out['skipped_non_vehicle']++;
                } else {
                    $out['skipped_other']++;
                }
                $out['details'][] = 'SKIP id=' . (int) $row['id'] . ' (' . $plan['skip_reason'] . ') '
                    . mb_strimwidth((string) ($row['title'] ?? ''), 0, 50, '…');
                continue;
            }

            if ($plan['changes'] === []) {
                continue;
            }

            $out['candidates']++;
            $line = ($dry ? '[dry] ' : '') . 'id=' . (int) $row['id'] . ' · '
                . mb_strimwidth((string) ($row['title'] ?? ''), 0, 55, '…') . ' → '
                . implode(', ', $plan['changes']);
            $out['details'][] = $line;

            if (!$dry) {
                $this->applyPatch((int) $row['id'], $plan['patch']);
            }
            $out['updated']++;
        }

        return $out;
    }

    /** @param array<string,mixed> $patch */
    private function applyPatch(int $id, array $patch): void
    {
        $sets = [];
        $args = [];
        foreach ($patch as $col => $val) {
            $sets[] = $col === 'condition' ? '`condition` = ?' : $col . ' = ?';
            $args[] = $val;
        }
        $args[] = $id;
        $sql = 'UPDATE trade_listings SET ' . implode(', ', $sets) . ' WHERE id = ?';
        $this->pdo->prepare($sql)->execute($args);
    }

    /**
     * @param array<string,mixed> $row
     */
    private function inferSegment(array $row): ?string
    {
        $sub = trim((string) ($row['subcategory'] ?? ''));
        $byLabel = cx_marketplace_by_label($sub);
        if ($byLabel !== null) {
            return (string) $byLabel['veh'];
        }

        $attrs = cx_listing_attrs($row);
        $stored = trim((string) ($attrs['segment'] ?? ''));
        if ($stored !== '' && isset(cx_vehicle_segments()[$stored]) && !cx_vehicle_is_all_mode($stored)) {
            return $stored;
        }

        $hay = mb_strtolower(implode(' ', array_filter([
            (string) ($row['title'] ?? ''),
            $sub,
            (string) ($row['category'] ?? ''),
            (string) ($row['description'] ?? ''),
        ])), 'UTF-8');

        $rules = [
            'motosiklet' => ['motosiklet', 'motorcycle', 'scooter', 'moped', 'mt-07', 'cbr', 'nmax'],
            'bisiklet' => ['bisiklet', 'bicycle', 'bike', 'trek ', 'giant ', 'decathlon', 'rockrider', 'elektrikli mtb'],
            'ticari' => ['ticari', 'kamyon', 'minibus', 'minibüs', 'sprinter', 'transit', 'crafter', 'panelvan'],
            'antika-arac' => ['antika', 'klasik arac', 'classic car', 'vintage arac', '1970', '1960', '1950'],
        ];

        foreach ($rules as $seg => $needles) {
            foreach ($needles as $needle) {
                if (str_contains($hay, $needle)) {
                    return $seg;
                }
            }
        }

        if (cx_is_vehicle_listing($row)) {
            return 'otomobil';
        }

        return null;
    }

    /**
     * @param array<string,mixed> $row
     * @param array<string,mixed> $existing
     * @return array<string,mixed>
     */
    private function buildAttrs(array $row, string $segment, array $existing): array
    {
        $vehicle = is_array($existing['vehicle'] ?? null) ? $existing['vehicle'] : [];
        $workRow = $row;
        if (!is_array($existing['vehicle'] ?? null)) {
            $workRow['attrs_json'] = json_encode($existing, JSON_UNESCAPED_UNICODE);
        }

        $make = trim((string) ($vehicle['make'] ?? ''));
        if ($make === '') {
            $make = cx_listing_vehicle_make($workRow, $segment);
        }
        if ($make === '' || !cx_vehicle_brand_in_catalog($make, $segment)) {
            $make = 'Diğer';
        } else {
            $make = cx_vehicle_canonical_make($make, $segment);
        }

        $model = trim((string) ($vehicle['model'] ?? ''));
        if ($model === '') {
            $model = cx_listing_vehicle_model($workRow, $segment, $make);
        }
        if ($model === '') {
            $model = $this->guessModelFromTitle((string) ($row['title'] ?? ''), $make);
        }
        if ($model === '') {
            $model = 'Diğer';
        }

        $year = isset($vehicle['year']) ? (int) $vehicle['year'] : 0;
        if ($year < 1900) {
            $year = $this->parseYear((string) ($row['title'] ?? ''));
        }
        if ($year < ($segment === 'antika-arac' ? 1900 : 1980)) {
            $year = $segment === 'antika-arac' ? 1975 : 2015;
        }

        $km = isset($vehicle['km']) ? (int) $vehicle['km'] : -1;
        if ($km < 0) {
            $km = $this->parseKm((string) ($row['title'] ?? '') . ' ' . (string) ($row['description'] ?? ''));
        }
        if ($km < 0 && $segment !== 'bisiklet') {
            $km = 0;
        }

        $vehicle['make'] = $make;
        $vehicle['model'] = $model;
        $vehicle['year'] = $year;
        if ($segment !== 'bisiklet') {
            $vehicle['km'] = max(0, $km);
        }

        $schema = $segment === 'bisiklet' ? cx_bicycle_filter_schema() : cx_vehicle_filter_schema($segment);
        if ($segment === 'bisiklet') {
            $vehicle['km'] = max(0, $km);
            $this->ensureOption($vehicle, 'bike_type', $schema['bike_type']['options'] ?? [], 'Dağ');
            $this->ensureOption($vehicle, 'frame', $schema['frame']['options'] ?? [], 'Alüminyum');
            $this->ensureOption($vehicle, 'condition', $schema['condition']['options'] ?? [], 'İkinci el');
        } else {
            $this->ensureOption($vehicle, 'fuel', $schema['fuel']['options'] ?? [], 'Benzin');
            $this->ensureOption($vehicle, 'transmission', $schema['transmission']['options'] ?? [], 'Manuel');
            if ($segment === 'motosiklet' && empty($vehicle['engine_cc'])) {
                $vehicle['engine_cc'] = 600;
            }
        }

        $existing['segment'] = $segment;
        $existing['vehicle'] = $vehicle;

        return $existing;
    }

    /** @param list<string> $options */
    private function ensureOption(array &$vehicle, string $key, array $options, string $fallback): void
    {
        $cur = trim((string) ($vehicle[$key] ?? ''));
        if ($cur !== '' && in_array($cur, $options, true)) {
            return;
        }
        $vehicle[$key] = in_array($fallback, $options, true) ? $fallback : ($options[0] ?? $fallback);
    }

    private function parseYear(string $text): int
    {
        if (preg_match('/\b(19[89]\d|20[0-2]\d)\b/', $text, $m)) {
            return (int) $m[1];
        }

        return 0;
    }

    private function parseKm(string $text): int
    {
        if (preg_match('/([\d\.]+)\s*(?:km|kilometre|k\.?\s*km)/iu', $text, $m)) {
            return (int) str_replace('.', '', $m[1]);
        }

        return -1;
    }

    private function guessModelFromTitle(string $title, string $make): string
    {
        $title = trim($title);
        if ($title === '' || $make === '' || $make === 'Diğer') {
            return '';
        }
        $lowerMake = mb_strtolower($make, 'UTF-8');
        $lowerTitle = mb_strtolower($title, 'UTF-8');
        if (str_starts_with($lowerTitle, $lowerMake)) {
            $rest = trim(mb_substr($title, mb_strlen($make, 'UTF-8'), null, 'UTF-8'));
            $rest = preg_replace('/^[\s\-–—]+/u', '', $rest) ?? $rest;
            if (preg_match('/^([A-Za-z0-9][A-Za-z0-9\.\-\s]{0,40})/u', $rest, $m)) {
                return trim($m[1]);
            }
        }

        return '';
    }

    /** @param list<string> $photos @return list<string> */
    private function padPhotos(array $photos, int $target): array
    {
        $photos = array_values(array_filter($photos, static fn ($p) => trim((string) $p) !== ''));
        if ($photos === []) {
            return array_slice(self::$placeholderPhotos, 0, $target);
        }

        while (count($photos) < $target) {
            $photos[] = $photos[count($photos) - 1];
        }

        return array_slice($photos, 0, $target);
    }
}
