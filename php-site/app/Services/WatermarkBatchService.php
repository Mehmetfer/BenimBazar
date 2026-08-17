<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

/** Mevcut ilan fotograflarina toplu filigran (orijinal _wm_backup altina alinir). */
final class WatermarkBatchService
{
    public static function backupDir(): string
    {
        $app = cx_app_config();
        $uploadDir = (string) ($app['uploads_path'] ?? (BASE_PATH . '/uploads'));

        return rtrim($uploadDir, '/\\') . '/_wm_backup';
    }

    /** @return list<string> */
    public static function collectLocalStubs(): array
    {
        $pdo = Database::pdo();
        $rows = $pdo->query('SELECT photo_urls FROM trade_listings WHERE photo_urls IS NOT NULL AND photo_urls <> \'[]\'')
            ->fetchAll(PDO::FETCH_COLUMN);
        $seen = [];
        foreach ($rows as $raw) {
            foreach (cx_listing_photo_stubs($raw) as $stub) {
                if (!self::isLocalStub($stub)) {
                    continue;
                }
                $seen[$stub] = true;
            }
        }

        $stubs = array_keys($seen);
        sort($stubs);

        return $stubs;
    }

    /**
     * @return array{
     *   total:int,processed:int,skipped:int,failed:int,backed_up:int,restored:int,
     *   errors:list<string>,samples:list<string>,done:bool,next_offset:int
     * }
     */
    public static function run(int $offset = 0, int $limit = 25, bool $dryRun = false): array
    {
        $stubs = self::collectLocalStubs();
        $total = count($stubs);
        $slice = array_slice($stubs, max(0, $offset), max(1, min(100, $limit)));

        $out = [
            'total' => $total,
            'processed' => 0,
            'skipped' => 0,
            'failed' => 0,
            'backed_up' => 0,
            'restored' => 0,
            'errors' => [],
            'samples' => [],
            'done' => ($offset + count($slice)) >= $total,
            'next_offset' => $offset + count($slice),
        ];

        if (!extension_loaded('gd')) {
            $out['errors'][] = 'GD extension yok — filigran uygulanamaz.';

            return $out;
        }

        $cfg = PhotoWatermarkService::burnConfig();
        if (!is_file($cfg['logo'])) {
            $out['errors'][] = 'Filigran logosu bulunamadi: ' . $cfg['logo'];

            return $out;
        }

        if (!$dryRun && !is_dir(self::backupDir())) {
            @mkdir(self::backupDir(), 0755, true);
            @file_put_contents(self::backupDir() . '/.htaccess', "Require all denied\n");
        }

        foreach ($slice as $stub) {
            $abs = self::localAbsolutePath($stub);
            if (!is_file($abs)) {
                $out['skipped']++;
                continue;
            }

            if ($dryRun) {
                $out['processed']++;
                if (count($out['samples']) < 8) {
                    $out['samples'][] = $stub;
                }
                continue;
            }

            $backupPath = self::backupPath($stub);
            $backupDir = dirname($backupPath);
            if (!is_dir($backupDir)) {
                @mkdir($backupDir, 0755, true);
            }

            if (is_file($backupPath)) {
                if (!@copy($backupPath, $abs)) {
                    $out['failed']++;
                    $out['errors'][] = 'Geri yukleme basarisiz: ' . $stub;
                    continue;
                }
                $out['restored']++;
            } elseif (!@copy($abs, $backupPath)) {
                $out['failed']++;
                $out['errors'][] = 'Yedek alinamadi: ' . $stub;
                continue;
            } else {
                $out['backed_up']++;
            }

            if (PhotoWatermarkService::applyToFile($abs, true)) {
                $out['processed']++;
                if (count($out['samples']) < 8) {
                    $out['samples'][] = $stub;
                }
            } else {
                @copy($backupPath, $abs);
                $out['failed']++;
                $out['errors'][] = 'Filigran basarisiz: ' . $stub;
            }
        }

        return $out;
    }

    /** @return array{local_files:int,with_backup:int,gd:bool,burn_on_upload:bool} */
    public static function stats(): array
    {
        $stubs = self::collectLocalStubs();
        $withBackup = 0;
        foreach ($stubs as $stub) {
            if (is_file(self::backupPath($stub))) {
                $withBackup++;
            }
        }
        $cfg = PhotoWatermarkService::burnConfig();

        return [
            'local_files' => count($stubs),
            'with_backup' => $withBackup,
            'gd' => extension_loaded('gd'),
            'burn_on_upload' => $cfg['burn_on_upload'],
        ];
    }

    public static function isLocalStub(string $stub): bool
    {
        $stub = trim($stub);
        if ($stub === '') {
            return false;
        }
        if (preg_match('#^https?://#i', $stub)) {
            return false;
        }
        if (str_starts_with($stub, '//')) {
            return false;
        }

        return true;
    }

    public static function localAbsolutePath(string $stub): string
    {
        $app = cx_app_config();
        $uploadDir = rtrim((string) ($app['uploads_path'] ?? (BASE_PATH . '/uploads')), '/\\');
        $stub = str_replace('\\', '/', trim($stub));
        $stub = ltrim($stub, '/');
        if (str_starts_with($stub, 'uploads/')) {
            $stub = substr($stub, strlen('uploads/'));
        }

        return $uploadDir . '/' . $stub;
    }

    public static function backupPath(string $stub): string
    {
        $stub = str_replace('\\', '/', trim($stub));
        $stub = ltrim($stub, '/');
        if (str_starts_with($stub, 'uploads/')) {
            $stub = substr($stub, strlen('uploads/'));
        }

        return self::backupDir() . '/' . $stub;
    }
}
