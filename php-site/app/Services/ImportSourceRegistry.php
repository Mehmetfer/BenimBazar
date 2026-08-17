<?php

declare(strict_types=1);

namespace App\Services;

/** Dis kaynak import profilleri (kibrisarabaal, kpazar, ozel site). */
final class ImportSourceRegistry
{
    /** @return array<string,array<string,mixed>> */
    public static function presets(): array
    {
        return [
            'kka' => [
                'key' => 'kka',
                'label' => 'kibrisarabaal.com',
                'domain' => 'kibrisarabaal.com',
                'queue_subdir' => 'kka-queue',
                'script' => 'python scripts/kibrisarabaal_build_queue.py',
                'default_date_from' => '2026-06-01',
                'default_date_to' => '',
                'hint' => 'Sterlin (£) korunur · ilan tarihi eskiden yeniye',
            ],
            'kpazar' => [
                'key' => 'kpazar',
                'label' => 'kpazar.com',
                'domain' => 'kpazar.com',
                'queue_subdir' => 'kpazar-queue',
                'script' => 'python scripts/kpazar_build_queue.py',
                'default_date_from' => '2026-06-01',
                'default_date_to' => '',
                'hint' => 'KKTC araba ilanlari · GBP/EUR/TRY',
            ],
        ];
    }

    /** @return array<string,array<string,mixed>> */
    public static function tabs(): array
    {
        $tabs = self::presets();
        $tabs['custom'] = [
            'key' => 'custom',
            'label' => 'Diger site',
            'domain' => '',
            'queue_subdir' => '',
            'script' => '',
            'default_date_from' => '2026-06-01',
            'default_date_to' => '',
            'hint' => 'Site adini (domain) girin; kuyruk: storage/import-queue/{site}/',
        ];

        return $tabs;
    }

    /**
     * @return array{key:string,label:string,domain:string,queue_dir:string,script:string,hint:string,default_date_from:string,default_date_to:string}
     */
    public static function resolve(string $sourceKey, string $customDomain = ''): array
    {
        $presets = self::presets();
        if ($sourceKey === 'custom') {
            $domain = self::normalizeDomain($customDomain);
            if ($domain === '') {
                throw new \RuntimeException('Ozel site icin domain girin (ornek: ornek.com).');
            }
            $slug = self::domainSlug($domain);

            return [
                'key' => 'custom',
                'label' => $domain,
                'domain' => $domain,
                'queue_dir' => self::storageRoot() . '/import-queue/' . $slug,
                'script' => '',
                'hint' => 'JSON kuyruk dosyalarini storage/import-queue/' . $slug . '/ altina koyun.',
                'default_date_from' => '2026-06-01',
                'default_date_to' => '',
            ];
        }

        if (!isset($presets[$sourceKey])) {
            $sourceKey = 'kka';
        }
        $p = $presets[$sourceKey];

        return [
            'key' => $sourceKey,
            'label' => (string) $p['label'],
            'domain' => (string) $p['domain'],
            'queue_dir' => self::storageRoot() . '/' . $p['queue_subdir'],
            'script' => (string) $p['script'],
            'hint' => (string) $p['hint'],
            'default_date_from' => (string) $p['default_date_from'],
            'default_date_to' => (string) ($p['default_date_to'] ?? ''),
        ];
    }

    public static function normalizeDomain(string $raw): string
    {
        $raw = trim(strtolower($raw));
        $raw = preg_replace('#^https?://#', '', $raw) ?? '';
        $raw = explode('/', $raw)[0] ?? '';
        $raw = preg_replace('/[^a-z0-9.\-]/', '', $raw) ?? '';

        return trim($raw, '.');
    }

    public static function domainSlug(string $domain): string
    {
        $slug = preg_replace('/[^a-z0-9]+/', '-', strtolower($domain)) ?? 'site';

        return trim($slug, '-') ?: 'site';
    }

    private static function storageRoot(): string
    {
        return dirname(__DIR__, 2) . '/storage';
    }
}
