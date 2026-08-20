<?php

declare(strict_types=1);

namespace App\Services;

use RuntimeException;

/** Import plani, tarih filtresi ve onayli aktarim. */
final class ImportQueueService
{
    private ExternalListingImportService $importer;

    public function __construct(?ExternalListingImportService $importer = null)
    {
        $this->importer = $importer ?? new ExternalListingImportService();
    }

    /** @return array<string,mixed> */
    public function loadPlan(): array
    {
        $path = $this->planPath();
        if (!is_file($path)) {
            return self::defaultPlan();
        }
        $raw = @file_get_contents($path);
        if ($raw === false || $raw === '') {
            return self::defaultPlan();
        }
        $data = json_decode($raw, true);

        return is_array($data) ? array_merge(self::defaultPlan(), $data) : self::defaultPlan();
    }

    /** @param array<string,mixed> $plan */
    public function savePlan(array $plan, array $actor): void
    {
        $plan['prepared_at'] = date('c');
        $plan['prepared_by'] = (int) ($actor['id'] ?? 0);
        $dir = dirname($this->planPath());
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        file_put_contents(
            $this->planPath(),
            json_encode($plan, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
        );
    }

    /**
     * @return array{
     *   total:int,in_range:int,out_of_range:int,imported:int,pending:int,
     *   next:?array<string,mixed>,preview:list<array<string,mixed>>,meta:?array<string,mixed>
     * }
     */
    public function analyze(string $queueDir, string $expectedSource, string $dateFrom, string $dateTo): array
    {
        $fromTs = self::dateToTs($dateFrom, false);
        $toTs = self::dateToTs($dateTo, true);

        $out = [
            'total' => 0,
            'in_range' => 0,
            'out_of_range' => 0,
            'imported' => 0,
            'pending' => 0,
            'next' => null,
            'preview' => [],
            'meta' => $this->readQueueMeta($queueDir),
        ];

        if (!is_dir($queueDir)) {
            return $out;
        }

        $files = glob($queueDir . '/*.json') ?: [];
        sort($files, SORT_NATURAL);
        $pendingItems = [];

        foreach ($files as $file) {
            $data = $this->readQueueItem($file);
            if ($data === null) {
                continue;
            }
            $source = (string) ($data['source'] ?? $expectedSource);
            if ($expectedSource !== '' && $source !== $expectedSource) {
                continue;
            }
            $out['total']++;
            $listedTs = self::listingTs($data);
            $inRange = self::inDateRange($listedTs, $fromTs, $toTs);
            if (!$inRange) {
                $out['out_of_range']++;
            } else {
                $out['in_range']++;
            }

            $sourceId = (int) ($data['source_id'] ?? 0);
            if ($sourceId > 0 && $this->importer->findBySource($source, $sourceId) !== null) {
                $out['imported']++;
                continue;
            }
            if (!$inRange) {
                continue;
            }

            $data['_queue_file'] = basename($file);
            $pendingItems[] = $data;
        }

        usort($pendingItems, static function (array $a, array $b): int {
            $da = (string) ($a['listed_at_iso'] ?? '');
            $db = (string) ($b['listed_at_iso'] ?? '');
            if ($da === $db) {
                return ((int) ($a['source_id'] ?? 0)) <=> ((int) ($b['source_id'] ?? 0));
            }

            return $da <=> $db;
        });

        $out['pending'] = count($pendingItems);
        if ($pendingItems !== []) {
            $out['next'] = $pendingItems[0];
            $out['preview'] = array_slice($pendingItems, 0, 12);
        }

        return $out;
    }

    /**
     * @param array<string,mixed> $resolvedSource
     * @return list<array{ok:bool,message:string}>
     */
    public function importBatch(array $resolvedSource, string $dateFrom, string $dateTo, int $limit, array $actor): array
    {
        if ($limit < 1) {
            throw new RuntimeException('Aktarim adedi en az 1 olmali.');
        }
        $limit = min(50, $limit);
        $analysis = $this->analyze(
            (string) $resolvedSource['queue_dir'],
            (string) $resolvedSource['domain'],
            $dateFrom,
            $dateTo
        );
        if ($analysis['pending'] === 0) {
            throw new RuntimeException('Secilen aralikta aktarilacak ilan yok.');
        }

        $results = [];
        $count = 0;
        while ($count < $limit) {
            $analysis = $this->analyze(
                (string) $resolvedSource['queue_dir'],
                (string) $resolvedSource['domain'],
                $dateFrom,
                $dateTo
            );
            if ($analysis['next'] === null) {
                break;
            }
            try {
                $result = $this->importer->importOne($analysis['next']);
                $results[] = ['ok' => true, 'message' => (string) $result['message']];
            } catch (\Throwable $e) {
                $results[] = ['ok' => false, 'message' => $e->getMessage()];
            }
            $count++;
        }

        cx_audit_log((int) $actor['id'], 'import.batch', 'external_listing', 0, [
            'source' => $resolvedSource['domain'] ?? '',
            'from' => $dateFrom,
            'to' => $dateTo,
            'count' => $count,
        ]);

        return $results;
    }

    /** @return array<string,mixed> */
    private static function defaultPlan(): array
    {
        return [
            'source_key' => 'kka',
            'custom_domain' => '',
            'date_from' => '2026-06-01',
            'date_to' => date('Y-m-d'),
            'approved' => false,
        ];
    }

    private function planPath(): string
    {
        return dirname(__DIR__, 2) . '/storage/import-plan.json';
    }

    /** @return array<string,mixed>|null */
    private function readQueueItem(string $file): ?array
    {
        if (!is_file($file) || !is_readable($file)) {
            return null;
        }
        $raw = @file_get_contents($file);
        if ($raw === false || $raw === '') {
            return null;
        }
        $data = json_decode($raw, true);

        return is_array($data) ? $data : null;
    }

    /** @return array<string,mixed>|null */
    private function readQueueMeta(string $queueDir): ?array
    {
        $local = $queueDir . '/.meta.json';
        if (is_file($local)) {
            $data = json_decode((string) file_get_contents($local), true);

            return is_array($data) ? $data : null;
        }
        $name = basename($queueDir);
        $map = [
            'kka-queue' => dirname(__DIR__, 3) . '/scripts/.kka-queue-meta.json',
            'kpazar-queue' => dirname(__DIR__, 3) . '/scripts/.kpazar-queue-meta.json',
        ];
        if (isset($map[$name]) && is_file($map[$name])) {
            $data = json_decode((string) file_get_contents($map[$name]), true);

            return is_array($data) ? $data : null;
        }

        return null;
    }

    /** @param array<string,mixed> $item */
    private static function listingTs(array $item): ?int
    {
        $iso = (string) ($item['listed_at_iso'] ?? '');
        if ($iso !== '' && preg_match('/^\d{4}-\d{2}-\d{2}$/', $iso)) {
            $ts = strtotime($iso . ' 12:00:00');

            return $ts !== false ? $ts : null;
        }
        $listed = (string) ($item['listed_at'] ?? '');
        if ($listed !== '') {
            $ts = strtotime($listed);

            return $ts !== false ? $ts : null;
        }

        return null;
    }

    private static function dateToTs(string $ymd, bool $endOfDay): ?int
    {
        $ymd = trim($ymd);
        if ($ymd === '' || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $ymd)) {
            return null;
        }
        $suffix = $endOfDay ? ' 23:59:59' : ' 00:00:00';
        $ts = strtotime($ymd . $suffix);

        return $ts !== false ? $ts : null;
    }

    private static function inDateRange(?int $listedTs, ?int $fromTs, ?int $toTs): bool
    {
        if ($listedTs === null) {
            return $fromTs === null && $toTs === null;
        }
        if ($fromTs !== null && $listedTs < $fromTs) {
            return false;
        }
        if ($toTs !== null && $listedTs > $toTs) {
            return false;
        }

        return true;
    }
}
