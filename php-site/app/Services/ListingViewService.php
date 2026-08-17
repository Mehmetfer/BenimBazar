<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

/** Ilan goruntulenme sayaci — IP+oturum dedup, bot filtresi. */
final class ListingViewService
{
    private const DEDUP_SECONDS = 1800;

    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
    }

    /** Goruntulenmeyi kaydet; true = sayac artti. */
    public function record(int $listingId, ?array $viewer = null): bool
    {
        if ($listingId <= 0 || self::isBot()) {
            return false;
        }

        $stmt = $this->pdo->prepare('SELECT id, owner_id, status FROM trade_listings WHERE id = ? LIMIT 1');
        $stmt->execute([$listingId]);
        $row = $stmt->fetch();
        if (!$row) {
            return false;
        }

        $status = strtoupper((string) ($row['status'] ?? ''));
        if (!cx_listing_is_public($status) && $status !== 'SOLD') {
            return false;
        }

        // Sahip kendi ilanini saydirma
        if ($viewer !== null && (int) ($viewer['id'] ?? 0) === (int) ($row['owner_id'] ?? 0)) {
            return false;
        }

        $ipHash = self::ipHash();
        $sessionId = self::sessionId();
        $uaHash = self::uaHash();
        $since = microtime(true) - self::DEDUP_SECONDS;

        $dup = $this->pdo->prepare(
            'SELECT id FROM listing_views
             WHERE listing_id = ? AND ip_hash = ? AND session_id = ? AND viewed_at >= ?
             LIMIT 1'
        );
        $dup->execute([$listingId, $ipHash, $sessionId, $since]);
        if ($dup->fetch()) {
            return false;
        }

        $now = microtime(true);
        $this->pdo->prepare(
            'INSERT INTO listing_views (listing_id, ip_hash, session_id, user_agent_hash, viewed_at)
             VALUES (?,?,?,?,?)'
        )->execute([$listingId, $ipHash, $sessionId, $uaHash, $now]);

        $this->pdo->prepare(
            'UPDATE trade_listings SET view_count = COALESCE(view_count, 0) + 1, updated_at = updated_at WHERE id = ?'
        )->execute([$listingId]);

        return true;
    }

    public static function isBot(): bool
    {
        $ua = strtolower((string) ($_SERVER['HTTP_USER_AGENT'] ?? ''));
        if ($ua === '') {
            return true;
        }
        $bots = [
            'bot', 'crawl', 'spider', 'slurp', 'facebookexternalhit',
            'whatsapp', 'telegram', 'preview', 'curl', 'wget', 'python-requests',
        ];
        foreach ($bots as $needle) {
            if (str_contains($ua, $needle)) {
                return true;
            }
        }

        return false;
    }

    private static function ipHash(): string
    {
        $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');

        return hash('sha256', $ip . '|' . (string) (cx_app_config()['view_salt'] ?? 'changex'));
    }

    private static function sessionId(): string
    {
        if (session_status() !== PHP_SESSION_ACTIVE) {
            return 'nosess';
        }

        return substr(hash('sha256', session_id()), 0, 32);
    }

    private static function uaHash(): string
    {
        return substr(hash('sha256', (string) ($_SERVER['HTTP_USER_AGENT'] ?? '')), 0, 32);
    }

    public function countForListing(int $listingId): int
    {
        $stmt = $this->pdo->prepare('SELECT COALESCE(view_count, 0) FROM trade_listings WHERE id = ?');
        $stmt->execute([$listingId]);
        $n = $stmt->fetchColumn();

        return (int) $n;
    }
}
