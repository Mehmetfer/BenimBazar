<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;
use Throwable;

final class MarketCompareService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
    }

    /**
     * Yalnızca gerçek benzer ilan fiyatları. Veri yetmezse uydurma yok.
     *
     * @param array<string,mixed> $item
     * @return array<string,mixed>|null
     */
    public function analyze(array $item): ?array
    {
        if (!cx_market_compare_enabled()) {
            return null;
        }

        $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
        if ($mode !== 'SALE' || !cx_is_vehicle_listing($item)) {
            return null;
        }

        $currentPrice = cx_listing_effective_price($item);
        if ($currentPrice === null || $currentPrice['amount'] <= 0) {
            return null;
        }

        $attrs = cx_listing_attrs($item);
        $attrs['_title'] = (string) ($item['title'] ?? '');
        $attrs['_location'] = (string) ($item['location'] ?? '');
        $fp = cx_market_compare_fingerprint($attrs);
        if ($fp === null) {
            return cx_market_compare_insufficient();
        }

        $cfg = cx_market_compare_settings();
        if (!in_array($fp['segment'], $cfg['segments'], true)) {
            return cx_market_compare_insufficient();
        }

        $segment = $fp['segment'];
        $make = cx_vehicle_canonical_make($fp['make'], $segment);
        $excludeId = (int) ($item['id'] ?? 0);
        $currency = strtoupper($currentPrice['currency']);

        $candidates = $this->fetchCandidates($make, $fp['model'], $segment, $excludeId, $cfg['max_fetch']);
        if ($candidates === []) {
            return cx_market_compare_insufficient();
        }

        foreach (['A', 'B', 'C'] as $tier) {
            $prices = $this->collectTierPrices($candidates, $fp, $segment, $tier, $currency);
            if (count($prices) < $cfg['min_samples']) {
                continue;
            }

            $stats = cx_market_compare_price_stats($prices);
            if ($stats['count'] < $cfg['min_samples'] || $stats['avg'] <= 0) {
                continue;
            }

            $verdict = cx_market_compare_verdict($currentPrice['amount'], $stats);

            return [
                'ok' => true,
                'insufficient' => false,
                'tier' => $tier,
                'context' => cx_market_compare_context_label($attrs, $tier),
                'count' => $stats['count'],
                'count_label' => $stats['count'] . ' benzer araç analiz edildi.',
                'currency' => $currency,
                'current' => $currentPrice['amount'],
                'current_label' => cx_market_compare_format_amount($currentPrice['amount'], $currency),
                'min' => $stats['min'],
                'max' => $stats['max'],
                'avg' => $stats['avg'],
                'median' => $stats['median'],
                'min_label' => cx_market_compare_format_amount($stats['min'], $currency),
                'max_label' => cx_market_compare_format_amount($stats['max'], $currency),
                'avg_label' => cx_market_compare_format_amount($stats['avg'], $currency),
                'median_label' => cx_market_compare_format_amount($stats['median'], $currency),
                'range_label' => cx_market_compare_format_amount($stats['min'], $currency)
                    . ' – '
                    . cx_market_compare_format_amount($stats['max'], $currency),
                'browse_url' => cx_market_compare_browse_url($attrs, $tier),
                'position' => $verdict['position'],
                'position_icon' => $verdict['position_icon'],
                'position_label' => $verdict['position_label'],
                'avg_diff_pct' => $verdict['avg_diff_pct'],
                'avg_diff_label' => $verdict['avg_diff_label'],
            ];
        }

        return cx_market_compare_insufficient();
    }

    /**
     * @return list<array<string,mixed>>
     */
    private function fetchCandidates(string $make, string $model, string $segment, int $excludeId, int $limit): array
    {
        $likeMake = '%' . str_replace(['%', '_'], ['\\%', '\\_'], $make) . '%';
        $likeModel = '%' . str_replace(['%', '_'], ['\\%', '\\_'], $model) . '%';
        $likeSeg = '%"segment":"' . str_replace(['%', '_'], ['\\%', '\\_'], $segment) . '"%';

        $sql = "SELECT l.id, l.title, l.status, l.listing_mode, l.price_tl, l.attrs_json, l.created_at, l.location
                FROM trade_listings l
                WHERE UPPER(COALESCE(l.status, '')) IN ('APPROVED', 'ACTIVE')
                  AND UPPER(COALESCE(l.listing_mode, '')) = 'SALE'
                  AND l.attrs_json IS NOT NULL AND l.attrs_json <> ''
                  AND l.attrs_json LIKE ?
                  AND l.attrs_json LIKE ?
                  AND l.attrs_json LIKE ?";
        $params = [$likeMake, $likeModel, $likeSeg];
        if ($excludeId > 0) {
            $sql .= ' AND l.id <> ?';
            $params[] = $excludeId;
        }
        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . (int) max(1, min(400, $limit));

        try {
            $stmt = $this->pdo->prepare($sql);
            $stmt->execute($params);

            return $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];
        } catch (Throwable) {
            return [];
        }
    }

    /**
     * @param list<array<string,mixed>> $candidates
     * @param array<string,mixed> $base
     * @return list<float>
     */
    private function collectTierPrices(
        array $candidates,
        array $base,
        string $segment,
        string $tier,
        string $currency
    ): array {
        $prices = [];

        foreach ($candidates as $row) {
            if (!is_array($row)) {
                continue;
            }

            $otherAttrs = cx_listing_attrs($row);
            $otherAttrs['_location'] = (string) ($row['location'] ?? '');
            $otherFp = cx_market_compare_fingerprint($otherAttrs);
            if ($otherFp === null) {
                continue;
            }

            if (!cx_market_compare_tier_match($tier, $base, $otherFp, $segment)) {
                continue;
            }

            $price = cx_listing_effective_price($row);
            if ($price === null || $price['amount'] <= 0) {
                continue;
            }
            if (strtoupper($price['currency']) !== $currency) {
                continue;
            }

            $prices[] = (float) $price['amount'];
        }

        return $prices;
    }
}
