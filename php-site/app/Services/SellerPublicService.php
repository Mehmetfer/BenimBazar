<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

require_once __DIR__ . '/ListingService.php';
require_once __DIR__ . '/ListingSchemaService.php';

/** Genel satıcı / kurumsal galeri profili ve yayındaki ilanları. */
final class SellerPublicService
{
    private PDO $pdo;
    private int $listingNoBase;

    public function __construct(int $listingNoBase = 1000000000)
    {
        $this->pdo = Database::pdo();
        $this->listingNoBase = $listingNoBase;
        ListingSchemaService::ensureUserColumns();
    }

    /** @return array<string,mixed>|null */
    public function findOwner(int $ownerId): ?array
    {
        if ($ownerId <= 0) {
            return null;
        }

        $optional = ['avatar_url', 'country', 'phone', 'phone_verified_at', 'city', 'email', 'gallery_name', 'website', 'about', 'gallery_banner', 'gallery_hours', 'vip_starts_at', 'vip_ends_at'];
        $cols = ['id', 'username', 'role', 'change_score', 'created_at', 'suspended'];
        foreach ($optional as $col) {
            if ($this->columnExists('users', $col)) {
                $cols[] = $col;
            }
        }

        $stmt = $this->pdo->prepare('SELECT ' . implode(', ', $cols) . ' FROM users WHERE id = ? LIMIT 1');
        $stmt->execute([$ownerId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$row || !empty($row['suspended'])) {
            return null;
        }

        $role = (string) ($row['role'] ?? 'user');
        $row['is_corporate'] = in_array($role, ['dealer', 'vip_kurumsal'], true);
        $row['avatar_url'] = trim((string) ($row['avatar_url'] ?? ''));
        $row['phone'] = trim((string) ($row['phone'] ?? ''));
        $row['city'] = trim((string) ($row['city'] ?? ''));
        $row['email'] = trim((string) ($row['email'] ?? ''));
        $row['gallery_name'] = trim((string) ($row['gallery_name'] ?? ''));
        $row['website'] = trim((string) ($row['website'] ?? ''));
        $row['about'] = trim((string) ($row['about'] ?? ''));
        $row['gallery_hours'] = cx_gallery_hours_normalize($row['gallery_hours'] ?? '');
        $row['display_name'] = $this->resolveDisplayName(
            $ownerId,
            $row['gallery_name'] !== '' ? $row['gallery_name'] : (string) ($row['username'] ?? 'Üye')
        );
        if ($row['gallery_name'] !== '') {
            $row['display_name'] = $row['gallery_name'];
        }
        $row['public_url'] = $row['is_corporate']
            ? '/galeri.php?id=' . $ownerId
            : '/satici.php?id=' . $ownerId;
        $row['hover_hint'] = $row['is_corporate']
            ? 'Mağazasına bak'
            : 'Kullanıcının diğer ilanlarını gör';

        return $row;
    }

    /**
     * Ana sayfa araması: kurumsal / VIP galeriler.
     *
     * @return list<array<string,mixed>>
     */
    public function searchGalleries(string $q, int $limit = 12): array
    {
        $q = trim($q);
        if ($q === '') {
            return [];
        }

        ListingSchemaService::ensureUserColumns();
        $this->forgetColumnCache('users');

        $optional = ['avatar_url', 'country', 'phone', 'phone_verified_at', 'city', 'email', 'gallery_name', 'website', 'about', 'gallery_banner', 'gallery_hours', 'vip_starts_at', 'vip_ends_at'];
        $cols = ['u.id', 'u.username', 'u.role', 'u.change_score', 'u.created_at', 'u.suspended'];
        foreach ($optional as $col) {
            if ($this->columnExists('users', $col)) {
                $cols[] = 'u.' . $col;
            }
        }

        $like = '%' . $q . '%';
        $where = ['u.username LIKE ?'];
        $args = [$like];
        if ($this->columnExists('users', 'gallery_name')) {
            $where[] = 'u.gallery_name LIKE ?';
            $args[] = $like;
        }
        if ($this->columnExists('users', 'city')) {
            $where[] = 'u.city LIKE ?';
            $args[] = $like;
        }
        if ($this->columnExists('users', 'about')) {
            $where[] = 'u.about LIKE ?';
            $args[] = $like;
        }

        $sql = 'SELECT ' . implode(', ', $cols) . '
                FROM users u
                WHERE COALESCE(u.suspended, 0) = 0
                  AND u.role IN (\'dealer\', \'vip_kurumsal\')
                  AND (' . implode(' OR ', $where) . ')
                ORDER BY
                  CASE WHEN u.role = \'vip_kurumsal\' THEN 0 ELSE 1 END,
                  u.id DESC
                LIMIT ' . max(1, min(30, $limit));

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($args);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];
        $out = [];
        foreach ($rows as $row) {
            $owner = $this->findOwner((int) ($row['id'] ?? 0));
            if ($owner === null || empty($owner['is_corporate'])) {
                continue;
            }
            $listings = $this->publicListings((int) $owner['id'], null, false);
            $stats = $this->galleryStats($owner, $listings, null);
            $owner['stats'] = $stats;
            $out[] = $owner;
        }

        return $out;
    }

    /**
     * Galeri dizini — kurumsal / VIP mağazalar.
     *
     * @param array{city?:string,role?:string,q?:string,min_listings?:int} $filters
     * @return array{items:list<array<string,mixed>>,total:int,page:int,pages:int}
     */
    public function listGalleries(array $filters = [], int $page = 1, int $limit = 24): array
    {
        ListingSchemaService::ensureUserColumns();
        $page = max(1, $page);
        $limit = max(1, min(48, $limit));
        $offset = ($page - 1) * $limit;

        $where = ['COALESCE(u.suspended, 0) = 0', "u.role IN ('dealer', 'vip_kurumsal')"];
        $args = [];

        $city = trim((string) ($filters['city'] ?? ''));
        if ($city !== '') {
            $where[] = 'COALESCE(u.city, \'\') LIKE ?';
            $args[] = '%' . $city . '%';
        }

        $role = trim((string) ($filters['role'] ?? ''));
        if ($role === 'vip') {
            $where[] = "u.role = 'vip_kurumsal'";
        } elseif ($role === 'dealer') {
            $where[] = "u.role = 'dealer'";
        }

        $q = trim((string) ($filters['q'] ?? ''));
        if ($q !== '') {
            $like = '%' . $q . '%';
            $or = ['u.username LIKE ?'];
            $args[] = $like;
            if ($this->columnExists('users', 'gallery_name')) {
                $or[] = 'u.gallery_name LIKE ?';
                $args[] = $like;
            }
            if ($this->columnExists('users', 'about')) {
                $or[] = 'u.about LIKE ?';
                $args[] = $like;
            }
            $where[] = '(' . implode(' OR ', $or) . ')';
        }

        $minListings = max(0, (int) ($filters['min_listings'] ?? 0));
        $liveSql = "(SELECT COUNT(*) FROM trade_listings l
            WHERE l.owner_id = u.id AND UPPER(l.status) IN ('APPROVED','ACTIVE'))";
        if ($minListings > 0) {
            $where[] = $liveSql . ' >= ' . $minListings;
        }

        $whereSql = implode(' AND ', $where);

        $countStmt = $this->pdo->prepare("SELECT COUNT(*) FROM users u WHERE {$whereSql}");
        $countStmt->execute($args);
        $total = (int) $countStmt->fetchColumn();

        $optional = ['avatar_url', 'city', 'gallery_name', 'about', 'gallery_banner'];
        $cols = ['u.id', 'u.username', 'u.role'];
        foreach ($optional as $col) {
            if ($this->columnExists('users', $col)) {
                $cols[] = 'u.' . $col;
            }
        }
        $cols[] = $liveSql . ' AS live_count';
        $since = microtime(true) - (30 * 86400);
        $cols[] = '(SELECT COUNT(*) FROM trade_listings nl WHERE nl.owner_id = u.id AND nl.created_at >= ' . $this->pdo->quote((string) $since) . " AND UPPER(nl.status) IN ('APPROVED','ACTIVE','SOLD')) AS new_last_30";

        $sql = 'SELECT ' . implode(', ', $cols) . "
                FROM users u
                WHERE {$whereSql}
                ORDER BY
                  CASE WHEN u.role = 'vip_kurumsal' THEN 0 ELSE 1 END,
                  live_count DESC,
                  COALESCE(u.gallery_name, u.username) ASC
                LIMIT {$limit} OFFSET {$offset}";

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($args);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];

        $items = [];
        foreach ($rows as $row) {
            $owner = $this->findOwner((int) ($row['id'] ?? 0));
            if ($owner === null || empty($owner['is_corporate'])) {
                continue;
            }
            $owner['live_count'] = (int) ($row['live_count'] ?? 0);
            $owner['stats'] = [
                'listings' => $owner['live_count'],
                'new_last_30' => (int) ($row['new_last_30'] ?? 0),
            ];
            $items[] = $owner;
        }

        $pages = $total > 0 ? (int) ceil($total / $limit) : 1;

        return [
            'items' => $items,
            'total' => $total,
            'page' => $page,
            'pages' => $pages,
        ];
    }

    /**
     * @return list<array<string,mixed>>
     */
    public function featuredGalleries(int $vipLimit = 6, int $dealerLimit = 6): array
    {
        $out = [];
        if ($vipLimit > 0) {
            $vip = $this->listGalleries(['role' => 'vip', 'min_listings' => 1], 1, $vipLimit);
            foreach ($vip['items'] as $item) {
                $out[] = $item;
            }
        }
        if ($dealerLimit > 0) {
            $dealers = $this->listGalleries(['role' => 'dealer', 'min_listings' => 1], 1, $dealerLimit);
            foreach ($dealers['items'] as $item) {
                $out[] = $item;
            }
        }

        return $out;
    }

    /**
     * @return list<array<string,mixed>>
     */
    public function publicListings(int $ownerId, ?int $viewerId = null, bool $includeSold = true): array
    {
        if ($ownerId <= 0) {
            return [];
        }

        $statusSql = $includeSold
            ? "UPPER(l.status) IN ('APPROVED','ACTIVE','SOLD')"
            : "UPPER(l.status) IN ('APPROVED','ACTIVE')";

        $sql = "SELECT l.*, u.username AS owner_username, u.role AS owner_role, u.change_score
                FROM trade_listings l
                JOIN users u ON u.id = l.owner_id
                WHERE l.owner_id = ? AND {$statusSql}
                ORDER BY
                  CASE WHEN UPPER(l.status) IN ('APPROVED','ACTIVE') THEN 0 ELSE 1 END,
                  l.created_at DESC
                LIMIT 200";

        try {
            $stmt = $this->pdo->prepare($sql);
            $stmt->execute([$ownerId]);
        } catch (\Throwable) {
            $stmt = $this->pdo->prepare(
                "SELECT l.*, u.username AS owner_username, u.change_score
                 FROM trade_listings l
                 JOIN users u ON u.id = l.owner_id
                 WHERE l.owner_id = ? AND {$statusSql}
                 ORDER BY l.created_at DESC
                 LIMIT 200"
            );
            $stmt->execute([$ownerId]);
        }

        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];

        return (new ListingService($this->listingNoBase))->enrichRows($rows, $viewerId);
    }

    /**
     * @param list<array<string,mixed>> $items
     * @return array{
     *   listings:int,active:int,favorites:int,views:int,member_year:int,banner:string,is_following:bool,new_last_30:int
     * }
     */
    public function galleryStats(array $owner, array $items, ?int $viewerId = null): array
    {
        $active = 0;
        $favorites = 0;
        $views = 0;
        $newLast30 = 0;
        $since = microtime(true) - (30 * 86400);
        $banner = trim((string) ($owner['gallery_banner'] ?? ''));
        if ($banner === '') {
            foreach ($items as $item) {
                $st = strtoupper((string) ($item['status'] ?? ''));
                if ($banner === '' && in_array($st, ['APPROVED', 'ACTIVE', 'SOLD'], true)) {
                    $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]');
                    if ($photos !== []) {
                        $banner = (string) $photos[0];
                    }
                }
            }
        }
        foreach ($items as $item) {
            $st = strtoupper((string) ($item['status'] ?? ''));
            if (in_array($st, ['APPROVED', 'ACTIVE'], true)) {
                $active++;
            }
            if ((float) ($item['created_at'] ?? 0) >= $since) {
                $newLast30++;
            }
            $favorites += (int) ($item['favorite_count'] ?? 0);
            $views += (int) ($item['view_count'] ?? 0);
        }

        $created = (float) ($owner['created_at'] ?? 0);
        $memberYear = $created > 0 ? (int) date('Y', (int) $created) : (int) date('Y');

        $isFollowing = false;
        $ownerId = (int) ($owner['id'] ?? 0);
        if ($viewerId && $ownerId > 0 && $viewerId !== $ownerId) {
            require_once __DIR__ . '/SocialService.php';
            $isFollowing = SocialService::isFollowing($viewerId, $ownerId);
        }

        return [
            'listings' => $active,
            'active' => $active,
            'favorites' => $favorites,
            'views' => $views,
            'member_year' => $memberYear,
            'banner' => $banner,
            'is_following' => $isFollowing,
            'new_last_30' => $newLast30,
        ];
    }

    public function updateAvatar(int $userId, string $relativeOrUrl): bool
    {
        if ($userId <= 0 || !$this->columnExists('users', 'avatar_url')) {
            return false;
        }
        $value = trim($relativeOrUrl);
        $stmt = $this->pdo->prepare('UPDATE users SET avatar_url = ? WHERE id = ?');

        return $stmt->execute([$value !== '' ? $value : null, $userId]);
    }

    /** VIP mağaza vitrin / arka plan görseli. */
    public function updateGalleryBanner(int $userId, string $relativeOrUrl): bool
    {
        ListingSchemaService::ensureUserColumns();
        $this->forgetColumnCache('users');
        if ($userId <= 0 || !$this->columnExists('users', 'gallery_banner')) {
            return false;
        }
        $value = trim($relativeOrUrl);
        $stmt = $this->pdo->prepare('UPDATE users SET gallery_banner = ? WHERE id = ?');

        return $stmt->execute([$value !== '' ? $value : null, $userId]);
    }

    /**
     * VIP / kurumsal galeri profil alanları.
     *
     * @param array{
     *   gallery_name?:string,phone?:string,city?:string,email?:string,
     *   website?:string,about?:string,gallery_hours?:string
     * } $data
     */
    public function updateCorporateProfile(int $userId, array $data): bool
    {
        if ($userId <= 0) {
            return false;
        }

        ListingSchemaService::ensureUserColumns();
        $this->forgetColumnCache('users');

        $galleryName = mb_substr(trim((string) ($data['gallery_name'] ?? '')), 0, 128);
        $phone = mb_substr(trim((string) ($data['phone'] ?? '')), 0, 32);
        $city = mb_substr(trim((string) ($data['city'] ?? '')), 0, 128);
        $email = mb_substr(trim((string) ($data['email'] ?? '')), 0, 255);
        $website = mb_substr(trim((string) ($data['website'] ?? '')), 0, 255);
        $about = mb_substr(trim((string) ($data['about'] ?? '')), 0, 500);
        $hours = trim((string) ($data['gallery_hours'] ?? ''));
        if ($hours !== '') {
            $hoursNorm = cx_gallery_hours_normalize($hours);
            $hours = cx_gallery_hours_has_any($hoursNorm)
                ? (json_encode($hoursNorm, JSON_UNESCAPED_UNICODE) ?: '')
                : '';
        }

        if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return false;
        }
        if ($website !== '' && !preg_match('#^https?://#i', $website)) {
            $website = 'https://' . ltrim($website, '/');
        }
        if ($website !== '' && !filter_var($website, FILTER_VALIDATE_URL)) {
            return false;
        }

        $sets = [];
        $args = [];
        $map = [
            'gallery_name' => $galleryName !== '' ? $galleryName : null,
            'phone' => $phone !== '' ? $phone : null,
            'city' => $city !== '' ? $city : null,
            'email' => $email !== '' ? $email : null,
            'website' => $website !== '' ? $website : null,
            'about' => $about !== '' ? $about : null,
            'gallery_hours' => $hours !== '' ? $hours : null,
        ];
        foreach ($map as $col => $val) {
            if (!$this->columnExists('users', $col)) {
                continue;
            }
            $sets[] = "`{$col}` = ?";
            $args[] = $val;
        }
        if ($sets === []) {
            return false;
        }
        $args[] = $userId;

        $sql = 'UPDATE users SET ' . implode(', ', $sets) . ' WHERE id = ?';
        $stmt = $this->pdo->prepare($sql);

        return $stmt->execute($args);
    }

    private function resolveDisplayName(int $ownerId, string $fallback): string
    {
        $stmt = $this->pdo->prepare(
            "SELECT attrs_json FROM trade_listings
             WHERE owner_id = ? AND attrs_json IS NOT NULL AND attrs_json <> ''
             ORDER BY created_at DESC LIMIT 12"
        );
        $stmt->execute([$ownerId]);
        foreach ($stmt->fetchAll(PDO::FETCH_COLUMN) as $raw) {
            $attrs = json_decode((string) $raw, true);
            if (!is_array($attrs)) {
                continue;
            }
            $seller = is_array($attrs['seller'] ?? null) ? $attrs['seller'] : [];
            $name = trim((string) ($seller['display_name'] ?? ''));
            if ($name !== '') {
                return $name;
            }
        }

        return $fallback !== '' ? $fallback : 'Üye';
    }

    private function forgetColumnCache(string $table): void
    {
        self::$columnCache = [];
    }

    /** @var array<string,bool> */
    private static array $columnCache = [];

    private function columnExists(string $table, string $column): bool
    {
        $key = $table . '.' . $column;
        if (array_key_exists($key, self::$columnCache)) {
            return self::$columnCache[$key];
        }
        try {
            $stmt = $this->pdo->query(
                'SHOW COLUMNS FROM `' . str_replace('`', '', $table) . '` LIKE ' . $this->pdo->quote($column)
            );
            self::$columnCache[$key] = (bool) ($stmt && $stmt->fetch());
        } catch (\Throwable) {
            self::$columnCache[$key] = false;
        }

        return self::$columnCache[$key];
    }
}
