<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Auth;
use App\Helpers\Database;
use PDO;
use RuntimeException;

/** Dis kaynaklardan (kibrisarabaal, kpazar, ...) ilan aktarimi. */
final class ExternalListingImportService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
    }

    /** @param array<string,mixed> $payload */
    public function importOne(array $payload): array
    {
        $source = trim((string) ($payload['source'] ?? 'kibrisarabaal.com'));
        $sourceId = (int) ($payload['source_id'] ?? 0);
        if ($sourceId <= 0) {
            throw new RuntimeException('source_id gerekli');
        }

        $existing = $this->findBySource($source, $sourceId);
        if ($existing !== null) {
            return [
                'skipped' => true,
                'listing_id' => (int) $existing['id'],
                'message' => 'Zaten aktarildi (' . $source . ' #' . $sourceId . ')',
            ];
        }

        $owner = $this->resolveOwner($payload);
        $photos = $this->resolvePhotos($payload, $source, $sourceId);
        $createdAt = $this->parseCreatedAt($payload);
        $attrs = $this->buildAttrs($payload);
        $priceMeta = $payload['price'] ?? null;
        $priceTl = null;
        if (is_array($priceMeta) && strtoupper((string) ($priceMeta['currency'] ?? '')) === 'TRY') {
            $priceTl = (float) ($priceMeta['amount'] ?? 0);
        }

        $stmt = $this->pdo->prepare(
            'INSERT INTO trade_listings (
              owner_id, title, description, category, subcategory, `condition`, location,
              mandal_units, accept_categories, wanted_items, min_mandal_units, max_mandal_units,
              photo_urls, attrs_json, status, listing_mode, price_tl, price_negotiable, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
        );
        $stmt->execute([
            (int) $owner['id'],
            (string) ($payload['title'] ?? 'Arac ilani'),
            (string) ($payload['description'] ?? ''),
            'Araclar',
            (string) ($payload['subcategory'] ?? 'Otomobil'),
            $this->mapCondition((string) ($payload['condition'] ?? '')),
            (string) ($payload['location'] ?? ''),
            0,
            '[]',
            '',
            0,
            0,
            json_encode($photos, JSON_UNESCAPED_UNICODE) ?: '[]',
            json_encode($attrs, JSON_UNESCAPED_UNICODE),
            'APPROVED',
            'SALE',
            $priceTl,
            !empty($payload['price_negotiable']) ? 1 : 0,
            $createdAt,
            $createdAt,
        ]);

        $listingId = (int) $this->pdo->lastInsertId();
        $this->ensureCorporateProfile($owner, $payload);
        (new ListingLifecycleService())->markPublished($listingId);

        return [
            'skipped' => false,
            'listing_id' => $listingId,
            'owner_id' => (int) $owner['id'],
            'photos' => count($photos),
            'message' => 'Aktarildi: ' . $source . ' #' . $sourceId . ' -> listing ' . $listingId,
        ];
    }

    /** @return array<string,mixed>|null */
    public function findBySource(string $source, int $sourceId): ?array
    {
        $stmt = $this->pdo->prepare(
            'SELECT id, owner_id, attrs_json FROM trade_listings WHERE attrs_json LIKE ?'
        );
        $stmt->execute(['%"source":' . json_encode($source, JSON_UNESCAPED_UNICODE) . '%']);
        while ($row = $stmt->fetch()) {
            $attrs = json_decode((string) ($row['attrs_json'] ?? ''), true);
            if (!is_array($attrs)) {
                continue;
            }
            $imp = $attrs['import'] ?? [];
            if (!is_array($imp)) {
                continue;
            }
            if ((string) ($imp['source'] ?? '') === $source && (int) ($imp['source_id'] ?? 0) === $sourceId) {
                return $row;
            }
        }

        return null;
    }

    /** @param array<string,mixed> $payload @return array<string,mixed> */
    private function resolveOwner(array $payload): array
    {
        $source = trim((string) ($payload['source'] ?? 'kibrisarabaal.com'));
        $prefix = $this->sourcePrefix($source);
        $sellerKey = trim((string) ($payload['seller_key'] ?? ''));
        if ($sellerKey === '') {
            $sellerKey = 'bireysel_' . substr(sha1((string) ($payload['seller_name'] ?? 'anon')), 0, 10);
        }

        $username = $prefix . preg_replace('/[^a-z0-9_]/', '_', strtolower($sellerKey));
        $username = substr($username, 0, 60);

        $stmt = $this->pdo->prepare('SELECT * FROM users WHERE username = ? LIMIT 1');
        $stmt->execute([$username]);
        $row = $stmt->fetch();
        if ($row) {
            if (!empty($payload['is_corporate'])) {
                $this->upgradeCorporateUser($row, $payload);
                $stmt->execute([$username]);
                $row = $stmt->fetch() ?: $row;
            }

            return $row;
        }

        $isCorporate = !empty($payload['is_corporate']);
        $role = $isCorporate ? 'vip_kurumsal' : 'user';
        $hash = Auth::hashPassword(bin2hex(random_bytes(12)));
        $memberYear = trim((string) ($payload['seller_member_since'] ?? ''));
        $createdAt = microtime(true);
        if ($memberYear !== '' && preg_match('/^\d{4}$/', $memberYear)) {
            $createdAt = (float) strtotime($memberYear . '-01-01 12:00:00');
        }

        ListingSchemaService::ensureUserColumns();
        $country = $this->sellerCountryFromPayload($payload);
        $this->pdo->prepare(
            'INSERT INTO users (username, password_hash, role, email, change_score, country, created_at, vip_starts_at, vip_ends_at)
             VALUES (?,?,?,?,?,?,?,?,?)'
        )->execute([
            $username,
            $hash,
            $role,
            null,
            $isCorporate ? 78 : 55,
            $country,
            $createdAt,
            $isCorporate ? date('Y-m-d') : null,
            $isCorporate ? date('Y-m-d', strtotime('+1 year')) : null,
        ]);

        $stmt->execute([$username]);
        $row = $stmt->fetch();
        if (!$row) {
            throw new RuntimeException('Kullanici olusturulamadi: ' . $username);
        }

        if ($isCorporate) {
            $this->applyGalleryProfile((int) $row['id'], $payload);
        }

        return $row;
    }

    /** @param array<string,mixed> $user @param array<string,mixed> $payload */
    private function upgradeCorporateUser(array $user, array $payload): void
    {
        $userId = (int) ($user['id'] ?? 0);
        if ($userId <= 0) {
            return;
        }
        $role = (string) ($user['role'] ?? 'user');
        if (!in_array($role, ['user', 'dealer'], true)) {
            $this->applyGalleryProfile($userId, $payload);

            return;
        }
        ListingSchemaService::ensureUserColumns();
        $this->pdo->prepare(
            'UPDATE users SET role = ?, country = ?, vip_starts_at = ?, vip_ends_at = ? WHERE id = ?'
        )->execute([
            'vip_kurumsal',
            'kktc',
            date('Y-m-d'),
            date('Y-m-d', strtotime('+1 year')),
            $userId,
        ]);
        $this->applyGalleryProfile($userId, $payload);
    }

    /** @param array<string,mixed> $owner @param array<string,mixed> $payload */
    private function ensureCorporateProfile(array $owner, array $payload): void
    {
        if (empty($payload['is_corporate'])) {
            return;
        }
        $this->applyGalleryProfile((int) ($owner['id'] ?? 0), $payload);
    }

    /** @param array<string,mixed> $payload */
    private function applyGalleryProfile(int $userId, array $payload): void
    {
        if ($userId <= 0) {
            return;
        }
        require_once __DIR__ . '/SellerPublicService.php';
        $city = $this->cityFromLocation((string) ($payload['location'] ?? ''));
        $about = trim((string) ($payload['gallery_about'] ?? ''));
        if ($about === '') {
            $about = trim((string) ($payload['description'] ?? ''));
        }
        (new SellerPublicService())->updateCorporateProfile($userId, [
            'gallery_name' => trim((string) ($payload['seller_name'] ?? '')),
            'phone' => trim((string) ($payload['seller_phone'] ?? '')),
            'city' => $city,
            'website' => trim((string) ($payload['seller_profile_url'] ?? '')),
            'about' => mb_substr($about, 0, 500),
        ]);
    }

    private function cityFromLocation(string $location): string
    {
        $location = trim($location);
        if ($location === '') {
            return '';
        }
        $parts = preg_split('/\s*[,\/]\s*/u', $location) ?: [];
        $first = trim((string) ($parts[0] ?? ''));

        return mb_substr($first, 0, 128);
    }

    /** @param array<string,mixed> $payload */
    private function sellerCountryFromPayload(array $payload): string
    {
        if (!empty($payload['is_corporate'])) {
            return 'kktc';
        }
        $price = $payload['price'] ?? null;
        if (is_array($price) && strtoupper((string) ($price['currency'] ?? '')) === 'GBP') {
            return 'kktc';
        }

        return 'tr';
    }

    private function sourcePrefix(string $source): string
    {
        return match ($source) {
            'kpazar.com' => 'kpz_',
            default => 'kka_',
        };
    }

    /** @param array<string,mixed> $payload @return list<string> */
    private function resolvePhotos(array $payload, string $source, int $sourceId): array
    {
        $prefix = $this->sourcePrefix($source);
        $subdir = 'ext-import';
        $local = $payload['local_photos'] ?? [];
        if (is_array($local) && $local !== []) {
            $out = [];
            foreach ($local as $rel) {
                $base = basename((string) $rel);
                if ($base !== '' && is_file($this->uploadsRoot() . '/' . $subdir . '/' . $base)) {
                    $out[] = '/uploads/' . $subdir . '/' . $base;
                }
            }
            if ($out !== []) {
                return $out;
            }
        }

        $urls = $payload['photo_urls'] ?? [];
        if (!is_array($urls)) {
            return [];
        }

        $dir = $this->uploadsRoot() . '/' . $subdir;
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }

        $saved = [];
        $i = 0;
        foreach ($urls as $url) {
            $url = (string) $url;
            if ($url === '') {
                continue;
            }
            $path = parse_url($url, PHP_URL_PATH) ?? '';
            $ext = strtolower(pathinfo($path, PATHINFO_EXTENSION));
            if (!in_array($ext, ['webp', 'jpg', 'jpeg', 'png'], true)) {
                $ext = 'webp';
            }
            $name = $prefix . $sourceId . '_' . $i . '.' . $ext;
            $target = $dir . '/' . $name;
            if ($this->downloadFile($url, $target)) {
                $saved[] = '/uploads/' . $subdir . '/' . $name;
            }
            $i++;
        }

        return $saved;
    }

    private function downloadFile(string $url, string $target): bool
    {
        $ctx = stream_context_create([
            'http' => [
                'timeout' => 45,
                'header' => "User-Agent: BenimBazarImport/1.0\r\n",
            ],
        ]);
        $bin = @file_get_contents($url, false, $ctx);
        if ($bin === false || $bin === '') {
            return false;
        }

        return file_put_contents($target, $bin) !== false;
    }

    private function uploadsRoot(): string
    {
        $cfg = cx_app_config();

        return (string) ($cfg['uploads_path'] ?? dirname(__DIR__, 2) . '/uploads');
    }

    /** @param array<string,mixed> $payload */
    private function parseCreatedAt(array $payload): float
    {
        $iso = (string) ($payload['listed_at_iso'] ?? '');
        if ($iso !== '') {
            $ts = strtotime($iso);
            if ($ts !== false) {
                return (float) $ts;
            }
        }

        return microtime(true);
    }

    /** @param array<string,mixed> $payload @return array<string,mixed> */
    private function buildAttrs(array $payload): array
    {
        $vehicle = is_array($payload['vehicle'] ?? null) ? $payload['vehicle'] : [];
        $typeLabel = trim((string) ($payload['seller_type_label'] ?? ''));
        $memberSince = trim((string) ($payload['seller_member_since'] ?? ''));
        $profileLine = trim((string) ($payload['seller_profile_line'] ?? ''));
        if ($profileLine === '' && ($typeLabel !== '' || $memberSince !== '')) {
            $parts = array_filter([$typeLabel, $memberSince !== '' ? 'Uye ' . $memberSince : '']);
            $profileLine = implode(' · ', $parts);
        }

        $sellerType = !empty($payload['is_corporate']) ? 'Galeri' : 'Sahibinden';
        if (stripos($typeLabel, 'galeri') !== false || stripos($typeLabel, 'kurumsal') !== false) {
            $sellerType = 'Galeri';
        }

        $seller = [
            'type' => $sellerType,
            'display_name' => trim((string) ($payload['seller_name'] ?? '')),
            'type_label' => $typeLabel,
            'member_since' => $memberSince,
            'profile_line' => $profileLine,
        ];
        if (!empty($payload['seller_phone'])) {
            $seller['phone'] = (string) $payload['seller_phone'];
        }
        if (!empty($payload['seller_profile_url'])) {
            $seller['profile_url'] = (string) $payload['seller_profile_url'];
        }

        $equipment = $payload['equipment'] ?? [];
        if (!is_array($equipment)) {
            $equipment = [];
        }

        $source = trim((string) ($payload['source'] ?? 'kibrisarabaal.com'));
        $attrs = [
            'segment' => (string) ($payload['segment'] ?? 'otomobil'),
            'vehicle' => $vehicle,
            'seller' => $seller,
            'import' => [
                'source' => $source,
                'source_id' => (int) ($payload['source_id'] ?? 0),
                'source_url' => (string) ($payload['source_url'] ?? ''),
                'listed_at' => (string) ($payload['listed_at'] ?? ''),
            ],
        ];
        if ($equipment !== []) {
            $attrs['equipment'] = array_values(array_filter(array_map('strval', $equipment)));
        }

        $price = $payload['price'] ?? null;
        if (is_array($price) && isset($price['currency'], $price['amount'])) {
            $cur = strtoupper((string) $price['currency']);
            if (in_array($cur, ['GBP', 'TRY', 'EUR'], true)) {
                $attrs['price'] = [
                    'currency' => $cur,
                    'amount' => (float) $price['amount'],
                ];
            }
        }

        return $attrs;
    }

    private function mapCondition(string $raw): string
    {
        $raw = mb_strtolower(trim($raw), 'UTF-8');
        if (str_contains($raw, 'sifir') || str_contains($raw, 'sıfır')) {
            return 'new';
        }

        return 'good';
    }

    /** @deprecated Galeri importunda vip_kurumsal kullaniliyor */
    private function maybePromoteDealer(array $owner, array $payload): void
    {
        // no-op — kurumsal aktarimda resolveOwner vip_kurumsal atar
    }

    /** @return array{total:int,done:int,pending:int,next:?array<string,mixed>,source:string} */
    public function queueStatus(string $queueDir, string $expectedSource = ''): array
    {
        if (!is_dir($queueDir)) {
            return ['total' => 0, 'done' => 0, 'pending' => 0, 'next' => null, 'source' => $expectedSource];
        }

        $files = glob($queueDir . '/*.json') ?: [];
        sort($files, SORT_NATURAL);
        $done = 0;
        $next = null;
        foreach ($files as $file) {
            if (!is_file($file) || !is_readable($file)) {
                continue;
            }
            $raw = @file_get_contents($file);
            if ($raw === false || $raw === '') {
                continue;
            }
            $data = json_decode($raw, true);
            if (!is_array($data)) {
                continue;
            }
            $source = (string) ($data['source'] ?? 'kibrisarabaal.com');
            if ($expectedSource !== '' && $source !== $expectedSource) {
                continue;
            }
            $sourceId = (int) ($data['source_id'] ?? 0);
            if ($sourceId > 0 && $this->findBySource($source, $sourceId) !== null) {
                $done++;
                continue;
            }
            if ($next === null) {
                $next = $data;
            }
        }

        $total = 0;
        foreach ($files as $file) {
            if (!is_file($file) || !is_readable($file)) {
                continue;
            }
            $raw = @file_get_contents($file);
            if ($raw === false || $raw === '') {
                continue;
            }
            $data = json_decode($raw, true);
            if (!is_array($data)) {
                continue;
            }
            $source = (string) ($data['source'] ?? 'kibrisarabaal.com');
            if ($expectedSource === '' || $source === $expectedSource) {
                $total++;
            }
        }

        return [
            'total' => $total,
            'done' => $done,
            'pending' => $total - $done,
            'next' => $next,
            'source' => $next !== null ? (string) ($next['source'] ?? $expectedSource) : $expectedSource,
        ];
    }
}
