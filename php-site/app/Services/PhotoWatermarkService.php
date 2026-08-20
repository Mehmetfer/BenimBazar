<?php

declare(strict_types=1);

namespace App\Services;

/** Upload sonrasi GD ile dosyaya filigran yakar (CSS katmani kapali kalir). */
final class PhotoWatermarkService
{
    /** @return array{burn_on_upload:bool,logo:string,width_ratio:float,opacity:int,margin_px:int,blur_passes:int,jpeg_quality:int} */
    public static function burnConfig(): array
    {
        $wm = cx_app_config()['photo_watermark'] ?? [];

        return [
            'burn_on_upload' => !empty($wm['burn_on_upload']),
            'logo' => self::resolveLogoPath($wm),
            'width_ratio' => max(0.06, min(0.35, (float) ($wm['burn_width_ratio'] ?? 0.18))),
            'opacity' => max(8, min(60, (int) ($wm['burn_opacity'] ?? 30))),
            'margin_px' => max(4, min(48, (int) ($wm['burn_margin_px'] ?? 14))),
            'blur_passes' => max(0, min(4, (int) ($wm['burn_blur_passes'] ?? 2))),
            'jpeg_quality' => max(75, min(95, (int) ($wm['burn_jpeg_quality'] ?? 88))),
        ];
    }

    public static function applyToFile(string $absolutePath, bool $force = false): bool
    {
        $cfg = self::burnConfig();
        if (!$force && !$cfg['burn_on_upload']) {
            return false;
        }
        if (!is_file($absolutePath) || !is_file($cfg['logo'])) {
            return false;
        }
        if (!extension_loaded('gd')) {
            @error_log('[BenimBazar] PhotoWatermark: GD extension missing');

            return false;
        }

        $mime = self::detectMime($absolutePath);
        $image = self::loadImage($absolutePath, $mime);
        if ($image === null) {
            return false;
        }

        if (!imageistruecolor($image)) {
            imagepalettetotruecolor($image);
        }

        $logo = self::loadLogoImage($cfg['logo']);
        if ($logo === false) {
            imagedestroy($image);

            return false;
        }

        $imgW = imagesx($image);
        $imgH = imagesy($image);
        if ($imgW < 80 || $imgH < 80) {
            imagedestroy($image);
            imagedestroy($logo);

            return false;
        }

        $logoW = imagesx($logo);
        $logoH = imagesy($logo);
        $targetW = max(32, (int) round($imgW * $cfg['width_ratio']));
        $targetH = max(16, (int) round($targetW * $logoH / max(1, $logoW)));
        if ($targetW > $imgW - 8 || $targetH > $imgH - 8) {
            $scale = min(($imgW - 8) / $targetW, ($imgH - 8) / $targetH, 1.0);
            $targetW = max(24, (int) round($targetW * $scale));
            $targetH = max(12, (int) round($targetH * $scale));
        }

        $wm = imagescale($logo, $targetW, $targetH, IMG_BILINEAR_FIXED);
        imagedestroy($logo);
        if ($wm === false) {
            imagedestroy($image);

            return false;
        }
        if (!imageistruecolor($wm)) {
            imagepalettetotruecolor($wm);
        }

        for ($i = 0; $i < $cfg['blur_passes']; $i++) {
            @imagefilter($wm, IMG_FILTER_GAUSSIAN_BLUR);
        }

        $x = max(0, $imgW - $targetW - $cfg['margin_px']);
        $y = max(0, $imgH - $targetH - $cfg['margin_px']);

        self::stampLogo($image, $wm, $x, $y, $cfg['opacity']);
        imagedestroy($wm);

        $ok = self::saveImage($image, $absolutePath, $mime, $cfg['jpeg_quality']);
        imagedestroy($image);

        return $ok;
    }

    /** @param array<string,mixed> $wm */
    private static function resolveLogoPath(array $wm): string
    {
        $rel = trim((string) ($wm['burn_logo'] ?? $wm['logo'] ?? ''));
        if ($rel === '') {
            $rel = cx_brand_asset_path('watermark') ?: cx_brand_asset_path('logo_icon');
        }
        if ($rel === '') {
            return '';
        }
        if (str_starts_with($rel, '/') && defined('BASE_PATH')) {
            return BASE_PATH . $rel;
        }

        return $rel;
    }

    private static function detectMime(string $path): string
    {
        $mime = (string) (@mime_content_type($path) ?: '');
        if ($mime !== '' && !in_array($mime, ['application/octet-stream', 'text/plain', 'binary/octet-stream'], true)) {
            return $mime;
        }

        return match (strtolower((string) pathinfo($path, PATHINFO_EXTENSION))) {
            'jpg', 'jpeg' => 'image/jpeg',
            'png' => 'image/png',
            'webp' => 'image/webp',
            'gif' => 'image/gif',
            default => $mime !== '' ? $mime : 'image/jpeg',
        };
    }

    private static function loadLogoImage(string $logoPath): \GdImage|false
    {
        $logo = @imagecreatefrompng($logoPath);
        if ($logo !== false) {
            return $logo;
        }
        if (!function_exists('imagecreatefromstring')) {
            return false;
        }
        $raw = @file_get_contents($logoPath);

        return ($raw !== false && $raw !== '') ? (@imagecreatefromstring($raw) ?: false) : false;
    }

    private static function loadImage(string $path, string $mime): ?\GdImage
    {
        foreach (array_unique([$mime, self::detectMime($path)]) as $candidate) {
            $image = match ($candidate) {
                'image/jpeg', 'image/jpg' => @imagecreatefromjpeg($path) ?: null,
                'image/png' => @imagecreatefrompng($path) ?: null,
                'image/webp' => function_exists('imagecreatefromwebp') ? (@imagecreatefromwebp($path) ?: null) : null,
                'image/gif' => @imagecreatefromgif($path) ?: null,
                default => null,
            };
            if ($image instanceof \GdImage) {
                return $image;
            }
        }

        if (function_exists('imagecreatefromstring')) {
            $raw = @file_get_contents($path);
            if ($raw !== false && $raw !== '') {
                $image = @imagecreatefromstring($raw);

                return $image instanceof \GdImage ? $image : null;
            }
        }

        return null;
    }

    private static function saveImage(\GdImage $image, string $path, string $mime, int $jpegQuality): bool
    {
        $mime = self::detectMime($path);
        if ($mime === 'image/png') {
            imagesavealpha($image, true);
            imagealphablending($image, false);

            return imagepng($image, $path, 6);
        }
        if ($mime === 'image/webp' && function_exists('imagewebp')) {
            return imagewebp($image, $path, 86);
        }

        return imagejpeg($image, $path, $jpegQuality);
    }

    private static function stampLogo(\GdImage $image, \GdImage $wm, int $x, int $y, int $opacityPct): void
    {
        $opacityPct = max(0, min(100, $opacityPct));
        imagealphablending($image, true);
        imagecopymerge($image, $wm, $x, $y, 0, 0, imagesx($wm), imagesy($wm), $opacityPct);
    }
}
