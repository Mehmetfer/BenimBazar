<?php

declare(strict_types=1);

namespace App\Services;

final class SeoSettingsService
{
    private static function filePath(): string
    {
        return dirname(__DIR__, 2) . '/storage/seo-settings.json';
    }

    /** @return array<string,mixed> */
    public static function read(): array
    {
        return cx_seo_settings();
    }

    /** @param array<string,mixed> $input */
    public static function save(array $input): void
    {
        $allowed = [
            'default_title', 'default_description', 'search_url_template',
            'google_site_verification', 'yandex_site_verification', 'bing_site_verification',
            'google_business_profile_url',
            'google_maps_url', 'google_place_id',
        ];
        $orgKeys = [
            'legal_name', 'short_name', 'description', 'email', 'telephone',
            'address_street', 'address_city', 'address_region', 'address_postal',
            'address_country', 'service_areas', 'opening_hours',
        ];
        $socialKeys = ['facebook', 'instagram', 'youtube', 'tiktok', 'linkedin', 'x'];

        $current = cx_seo_settings();
        $out = $current;

        foreach ($allowed as $key) {
            if (array_key_exists($key, $input)) {
                $out[$key] = trim((string) $input[$key]);
            }
        }

        if (!isset($out['organization']) || !is_array($out['organization'])) {
            $out['organization'] = [];
        }
        foreach ($orgKeys as $key) {
            $field = 'org_' . $key;
            if (array_key_exists($field, $input)) {
                $out['organization'][$key] = trim((string) $input[$field]);
            }
        }

        if (!isset($out['social']) || !is_array($out['social'])) {
            $out['social'] = [];
        }
        foreach ($socialKeys as $key) {
            $field = 'social_' . $key;
            if (array_key_exists($field, $input)) {
                $val = trim((string) $input[$field]);
                if ($val !== '' && !preg_match('#^https?://#i', $val)) {
                    throw new \RuntimeException('Sosyal medya URL\'leri http(s) ile başlamalı: ' . $key);
                }
                $out['social'][$key] = $val;
            }
        }

        foreach (['google_business_profile_url', 'google_maps_url'] as $urlKey) {
            $val = trim((string) ($out[$urlKey] ?? ''));
            if ($val !== '' && !preg_match('#^https?://#i', $val)) {
                throw new \RuntimeException('Google URL alanları geçerli http(s) adresi olmalı.');
            }
        }

        unset($out['site_name'], $out['tagline']);
        $file = self::filePath();
        $dir = dirname($file);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        $json = json_encode($out, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($json === false || file_put_contents($file, $json) === false) {
            throw new \RuntimeException('SEO ayarları kaydedilemedi.');
        }
    }
}
