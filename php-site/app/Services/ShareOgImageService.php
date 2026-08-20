<?php

declare(strict_types=1);

namespace App\Services;

use RuntimeException;

/** WhatsApp / Open Graph paylasim gorseli (1200x630 PNG). */
final class ShareOgImageService
{
    private const W = 1200;
    private const H = 630;
    private const PHOTO_H = 400;
    private const BRAND_GREEN = [111, 191, 74];

    /** @param array<string,mixed> $item */
    public static function cachePath(array $item): string
    {
        $cfg = cx_app_config();
        $root = (string) ($cfg['uploads_path'] ?? dirname(__DIR__, 2) . '/uploads');
        $dir = $root . '/share-og';
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        $id = (int) ($item['id'] ?? 0);
        $ver = substr(sha1((string) ($item['updated_at'] ?? '') . '|' . (string) ($item['photo_urls'] ?? '') . '|wa-jpg-v2'), 0, 12);

        return $dir . '/listing-' . $id . '-' . $ver . '.jpg';
    }

    /** @param array<string,mixed> $item */
    public static function ensure(array $item, array $appConfig): string
    {
        $path = self::cachePath($item);
        if (is_file($path) && filesize($path) > 1000) {
            return $path;
        }
        self::renderToFile($item, $appConfig, $path);

        return $path;
    }

    /** Statik PNG URL (WhatsApp / Facebook onizleme icin PHP degil dosya yolu). */
    public static function publicUrl(string $cachePath, array $appConfig): string
    {
        $siteUrl = rtrim((string) ($appConfig['url'] ?? ''), '/');
        $uploadsUrl = rtrim((string) ($appConfig['uploads_url'] ?? '/uploads'), '/');
        $uploadsPath = str_replace('\\', '/', (string) ($appConfig['uploads_path'] ?? ''));
        $cachePath = str_replace('\\', '/', $cachePath);
        if ($uploadsPath !== '' && str_starts_with($cachePath, $uploadsPath)) {
            $rel = ltrim(substr($cachePath, strlen($uploadsPath)), '/');

            return $siteUrl . $uploadsUrl . '/' . $rel;
        }

        return $siteUrl . $uploadsUrl . '/share-og/' . basename($cachePath);
    }

    /** @param array<string,mixed> $item */
    public static function renderToFile(array $item, array $appConfig, string $target): void
    {
        if (!function_exists('imagecreatetruecolor')) {
            throw new RuntimeException('PHP GD eklentisi gerekli (share-og).');
        }

        $base = (int) ($appConfig['listing_no_base'] ?? 1000000000);
        $listingNo = (int) ($item['listing_no'] ?? cx_listing_no((int) ($item['id'] ?? 0), $base));
        $panel = cx_share_card_panel_fields($item, $listingNo);
        $headline = cx_share_card_headline($item);

        $img = imagecreatetruecolor(self::W, self::H);
        $black = imagecolorallocate($img, 5, 5, 5);
        $white = imagecolorallocate($img, 255, 255, 255);
        $gold = imagecolorallocate($img, self::BRAND_GREEN[0], self::BRAND_GREEN[1], self::BRAND_GREEN[2]);
        $muted = imagecolorallocate($img, 210, 216, 224);
        imagefill($img, 0, 0, $black);

        self::drawPhoto($img, $item, $appConfig);
        imagefilledrectangle($img, 0, self::PHOTO_H, self::W, self::PHOTO_H + 6, $gold);
        imagefilledrectangle($img, 0, self::PHOTO_H + 6, self::W, self::H, $black);
        imagerectangle($img, 2, self::PHOTO_H + 2, self::W - 3, self::H - 3, $gold);

        $bold = self::font('bold');
        $semi = self::font('semi');
        $y = self::PHOTO_H + 34;

        $titleLines = self::wrapText($headline, $bold, 34, self::W - 80);
        foreach ($titleLines as $line) {
            imagettftext($img, 34, 0, 40, $y, $white, $bold, $line);
            $y += 42;
        }

        $metaLeft = trim(($panel['year_label'] !== '' ? $panel['year_label'] . '   ' : '') . $panel['price_display']);
        imagettftext($img, 22, 0, 40, $y + 8, $white, $semi, self::fitText($metaLeft, $semi, 22, self::W - 80));
        $y += 34;
        imageline($img, 40, $y, self::W - 40, $y, $white);
        imageline($img, 40, $y + 3, self::W - 40, $y + 3, $gold);
        $y += 28;

        $footer = implode('   |   ', array_filter([
            $panel['fuel'],
            $panel['transmission'],
            $panel['location'],
            $panel['listing_ref'],
        ]));
        imagettftext($img, 17, 0, 40, $y, $muted, $semi, self::fitText($footer, $semi, 17, self::W - 80));

        imagettftext($img, 20, 0, self::W - 260, self::H - 28, $gold, $bold, cx_site_name());

        $dir = dirname($target);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        self::saveOptimizedJpeg($img, $target);
        imagedestroy($img);
    }

    private static function saveOptimizedJpeg(\GdImage $img, string $target): void
    {
        $qualities = [82, 75, 68, 60, 52, 45];
        foreach ($qualities as $quality) {
            ob_start();
            imagejpeg($img, null, $quality);
            $bin = ob_get_clean();
            if (!is_string($bin) || $bin === '') {
                continue;
            }
            if (strlen($bin) <= 280000) {
                if (file_put_contents($target, $bin) === false) {
                    throw new RuntimeException('JPEG yazilamadi: ' . $target);
                }

                return;
            }
        }

        if (!imagejpeg($img, $target, 40)) {
            throw new RuntimeException('JPEG yazilamadi: ' . $target);
        }
    }

    /** @param array<string,mixed> $item */
    private static function drawPhoto(\GdImage $canvas, array $item, array $appConfig): void
    {
        $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '');
        $hero = $photos[0] ?? '';
        if ($hero === '') {
            $bg = imagecolorallocate($canvas, 30, 35, 45);
            imagefilledrectangle($canvas, 0, 0, self::W, self::PHOTO_H, $bg);

            return;
        }

        $siteUrl = rtrim((string) ($appConfig['url'] ?? ''), '/');
        $hero = cx_photo_sized($hero, 1600, $siteUrl);

        $src = self::loadImage($hero, $appConfig);
        if ($src === null) {
            $bg = imagecolorallocate($canvas, 30, 35, 45);
            imagefilledrectangle($canvas, 0, 0, self::W, self::PHOTO_H, $bg);

            return;
        }

        $sw = imagesx($src);
        $sh = imagesy($src);
        $scale = max(self::W / $sw, self::PHOTO_H / $sh);
        $dw = (int) round($sw * $scale);
        $dh = (int) round($sh * $scale);
        $ox = (int) round((self::W - $dw) / 2);
        $oy = (int) round((self::PHOTO_H - $dh) / 2);
        imagecopyresampled($canvas, $src, $ox, $oy, 0, 0, $dw, $dh, $sw, $sh);
        imagedestroy($src);
    }

    /** @param array<string,mixed> $appConfig */
    private static function loadImage(string $path, array $appConfig): ?\GdImage
    {
        $uploadsPath = (string) ($appConfig['uploads_path'] ?? dirname(__DIR__, 2) . '/uploads');
        $siteUrl = rtrim((string) ($appConfig['url'] ?? ''), '/');

        if (str_starts_with($path, '/uploads/')) {
            $local = $uploadsPath . substr($path, strlen('/uploads'));
            if (is_file($local)) {
                return self::openImageFile($local);
            }
        }

        if (preg_match('#^https?://#i', $path)) {
            $bin = self::fetchBytes($path);
        } else {
            $abs = cx_absolute_url($path, $siteUrl);
            if (str_starts_with($abs, $siteUrl) && str_contains($abs, '/uploads/')) {
                $local = $uploadsPath . substr(parse_url($abs, PHP_URL_PATH) ?? '', strlen('/uploads'));
                if (is_file($local)) {
                    return self::openImageFile($local);
                }
            }
            $bin = self::fetchBytes($abs);
        }

        if ($bin === null || $bin === '') {
            return null;
        }
        $tmp = @imagecreatefromstring($bin);

        return $tmp instanceof \GdImage ? $tmp : null;
    }

    private static function openImageFile(string $file): ?\GdImage
    {
        $ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
        $img = match ($ext) {
            'jpg', 'jpeg' => @imagecreatefromjpeg($file),
            'png' => @imagecreatefrompng($file),
            'webp' => function_exists('imagecreatefromwebp') ? @imagecreatefromwebp($file) : false,
            default => false,
        };

        return $img instanceof \GdImage ? $img : null;
    }

    private static function fetchBytes(string $url): ?string
    {
        if (function_exists('curl_init')) {
            $ch = curl_init($url);
            if ($ch === false) {
                return null;
            }
            curl_setopt_array($ch, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_FOLLOWLOCATION => true,
                CURLOPT_TIMEOUT => 20,
                CURLOPT_USERAGENT => 'BenimBazarShareOg/1.0',
            ]);
            $raw = curl_exec($ch);
            curl_close($ch);

            return is_string($raw) ? $raw : null;
        }

        $ctx = stream_context_create([
            'http' => ['timeout' => 20, 'header' => "User-Agent: BenimBazarShareOg/1.0\r\n"],
        ]);
        $raw = @file_get_contents($url, false, $ctx);

        return is_string($raw) ? $raw : null;
    }

    private static function font(string $weight): string
    {
        $map = [
            'bold' => BASE_PATH . '/assets/fonts/Montserrat-Bold.ttf',
            'semi' => BASE_PATH . '/assets/fonts/Montserrat-SemiBold.ttf',
        ];
        $path = $map[$weight] ?? $map['bold'];
        if (is_file($path)) {
            return $path;
        }
        foreach ([
            'C:\\Windows\\Fonts\\arialbd.ttf',
            'C:\\Windows\\Fonts\\arial.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ] as $fallback) {
            if (is_file($fallback)) {
                return $fallback;
            }
        }

        throw new RuntimeException('Font bulunamadi (assets/fonts/Montserrat-*.ttf).');
    }

    /** @return list<string> */
    private static function wrapText(string $text, string $font, int $size, int $maxWidth): array
    {
        $words = preg_split('/\s+/u', trim($text)) ?: [];
        $lines = [];
        $line = '';
        foreach ($words as $word) {
            $try = $line === '' ? $word : $line . ' ' . $word;
            if (self::textWidth($try, $font, $size) <= $maxWidth) {
                $line = $try;
                continue;
            }
            if ($line !== '') {
                $lines[] = $line;
            }
            $line = $word;
        }
        if ($line !== '') {
            $lines[] = $line;
        }

        return $lines !== [] ? array_slice($lines, 0, 2) : [''];
    }

    private static function fitText(string $text, string $font, int $size, int $maxWidth): string
    {
        $text = trim($text);
        if (self::textWidth($text, $font, $size) <= $maxWidth) {
            return $text;
        }
        while ($text !== '' && self::textWidth($text . '…', $font, $size) > $maxWidth) {
            $text = mb_substr($text, 0, mb_strlen($text, 'UTF-8') - 1, 'UTF-8');
        }

        return rtrim($text) . '…';
    }

    private static function textWidth(string $text, string $font, int $size): int
    {
        $box = imagettfbbox($size, 0, $font, $text);
        if (!is_array($box)) {
            return 0;
        }

        return (int) abs($box[2] - $box[0]);
    }
}
