<?php

declare(strict_types=1);

namespace App\Services;

final class ShareCardService
{
    /** @return array<string,mixed> */
    public static function build(array $item, array $appConfig, string $format = 'square'): array
    {
        $siteUrl = rtrim((string) ($appConfig['url'] ?? ''), '/');
        $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '');
        $hero = $photos[0] ?? '';
        if ($hero !== '') {
            $hero = cx_photo_sized($hero, 1600, $siteUrl);
        }

        require_once dirname(__DIR__) . '/Helpers/vehicle-brands.php';
        $make = cx_listing_vehicle_make($item);
        $logoUrl = '';
        if ($make !== '') {
            $seg = (string) (cx_listing_attrs($item)['segment'] ?? 'otomobil');
            $canonicalMake = cx_vehicle_canonical_make($make, $seg);
            foreach (cx_vehicle_brand_catalog($seg) as $brand) {
                if (($brand['name'] ?? '') === $canonicalMake) {
                    $paths = cx_vehicle_brand_logo_paths($brand['name'], $brand['domain']);
                    $logoUrl = $paths[0] ?? '';
                    break;
                }
            }
            if ($logoUrl !== '') {
                $logoUrl = cx_absolute_url($logoUrl, $siteUrl);
            }
        }

        if ($logoUrl === '') {
            $iconPath = cx_brand_asset_path('logo_icon');
            if ($iconPath !== '') {
                $logoUrl = cx_absolute_url($iconPath, $siteUrl);
            }
        }

        $listingNo = (int) ($item['listing_no'] ?? 0);
        $format = $format === 'story' ? 'story' : 'square';
        $panel = cx_share_card_panel_fields($item, $listingNo);

        return [
            'format' => $format,
            'width' => 1080,
            'height' => $format === 'story' ? 1920 : 1080,
            'headline' => cx_share_card_headline($item),
            'year_label' => $panel['year_label'],
            'price_display' => $panel['price_display'],
            'fuel' => $panel['fuel'],
            'transmission' => $panel['transmission'],
            'location' => $panel['location'],
            'listing_ref' => $panel['listing_ref'],
            'hero_url' => $hero,
            'logo_url' => $logoUrl,
            'listing_no' => $listingNo,
            'share_url' => cx_share_url($listingNo, $siteUrl),
            'hashtags' => cx_share_card_hashtags($item),
            'caption' => cx_share_card_caption($item, $listingNo, $siteUrl),
            'brand' => cx_site_name(),
        ];
    }
}
