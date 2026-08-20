<?php
declare(strict_types=1);
/**
 * Tablo kurulumu + canli deploy alici (deployrecv).
 * Form anahtari: config/setup.local.php (production'da 404).
 */

/** HTTP deploy — deploy_live_php.py bu endpoint'i kullanir (ayri dosya gerekmez). */
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
    $islem = (string) ($_POST['islem'] ?? '');
    if ($islem === 'deployrecv' || $islem === 'deployget') {
    header('Content-Type: application/json; charset=utf-8');
    ini_set('display_errors', '0');

    $secret = (string) ($_POST['secret'] ?? '');
    $cfgPath = __DIR__ . '/config/deploy.local.php';
    $okSecret = false;
    if (is_file($cfgPath)) {
        /** @var array<string,mixed> $dc */
        $dc = require $cfgPath;
        $okSecret = hash_equals((string) ($dc['secret'] ?? ''), $secret);
    }
    if (!$okSecret) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'secret']);
        exit;
    }

    $rel = str_replace('\\', '/', (string) ($_POST['path'] ?? ''));
    $rel = ltrim($rel, '/');
    if ($rel === '' || str_contains($rel, '..')) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'invalid path']);
        exit;
    }
    $blocked = ['config/database.php', 'config/database.local.php', 'config/google.local.php', 'config/setup.local.php'];
    if (in_array($rel, $blocked, true) || str_starts_with($rel, 'config/deploy.local.php')) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'blocked']);
        exit;
    }

    if ($islem === 'deployget') {
        $target = __DIR__ . '/' . $rel;
        if (!is_file($target)) {
            http_response_code(404);
            echo json_encode(['ok' => false, 'error' => 'not found']);
            exit;
        }
        $content = file_get_contents($target);
        if ($content === false) {
            http_response_code(500);
            echo json_encode(['ok' => false, 'error' => 'read failed']);
            exit;
        }
        echo json_encode([
            'ok' => true,
            'path' => $rel,
            'bytes' => strlen($content),
            'content_b64' => base64_encode($content),
        ]);
        exit;
    }

    $raw = (string) ($_POST['content_b64'] ?? '');
    $content = base64_decode($raw, true);
    if ($content === false) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'bad content']);
        exit;
    }

    $target = __DIR__ . '/' . $rel;
    $dir = dirname($target);
    if (!is_dir($dir)) {
        mkdir($dir, 0755, true);
    }
    if (file_put_contents($target, $content) === false) {
        http_response_code(500);
        echo json_encode(['ok' => false, 'error' => 'write failed']);
        exit;
    }
    echo json_encode(['ok' => true, 'path' => $rel, 'bytes' => strlen($content)]);
    exit;
    }
}

/** @var array<string,mixed> $cxAppCfg */
$cxAppCfg = require __DIR__ . '/config/app.php';
if (!empty($cxAppCfg['production'])) {
    http_response_code(404);
    exit;
}

ini_set('display_errors', '1');
error_reporting(E_ALL);
header('Content-Type: text/html; charset=utf-8');

$messages = [];
$anahtar = (string) ($_POST['anahtar'] ?? '');
$islem = (string) ($_POST['islem'] ?? '');

require __DIR__ . '/bootstrap.php';

if (!cx_is_production()) {
    $setupPath = __DIR__ . '/config/setup.local.php';
    if (!is_file($setupPath)) {
        if (!is_dir(__DIR__ . '/config')) {
            mkdir(__DIR__ . '/config', 0755, true);
        }
        $generatedKey = bin2hex(random_bytes(16));
        file_put_contents(
            $setupPath,
            "<?php\nreturn ['setup_key' => " . var_export($generatedKey, true) . "];\n"
        );
        $messages[] = 'config/setup.local.php olusturuldu. Kurulum anahtariniz: ' . $generatedKey;
    }
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!cx_verify_setup_key($anahtar)) {
        $messages[] = 'HATA: Yanlis kurulum anahtari (config/setup.local.php)';
    } else {
        try {
            cx_bootstrap(false);
            $cfg = cx_load_db_config();
            App\Helpers\Database::connect($cfg);
            $pdo = App\Helpers\Database::pdo();
            $messages[] = 'MySQL baglanti OK';

            if ($islem === 'superpass') {
                $newPass = (string) ($_POST['new_password'] ?? '');
                if (strlen($newPass) < 12) {
                    throw new RuntimeException('Yeni superadmin sifresi en az 12 karakter olmali.');
                }
                $hash = App\Helpers\Auth::hashPassword($newPass);
                $pdo->prepare(
                    'INSERT INTO users (username, password_hash, role, created_at)
                     VALUES (?,?,?,?)
                     ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), role = VALUES(role)'
                )->execute(['superadmin', $hash, 'superadmin', microtime(true)]);
                $messages[] = 'superadmin sifresi guncellendi.';
            } elseif ($islem === 'cargrseed') {
                require_once __DIR__ . '/app/Services/CarGrDiverseSeedService.php';
                foreach (\App\Services\CarGrDiverseSeedService::seed() as $m) {
                    $messages[] = $m;
                }
            } elseif ($islem === 'vehicleseed') {
                require_once __DIR__ . '/app/Services/VehicleMarketSeedService.php';
                foreach (\App\Services\VehicleMarketSeedService::seed() as $m) {
                    $messages[] = $m;
                }
            } elseif ($islem === 'demo') {
                require_once __DIR__ . '/app/Services/DemoSeedService.php';
                foreach (\App\Services\DemoSeedService::seed() as $m) {
                    $messages[] = $m;
                }
            } elseif ($islem === 'migrate') {
                foreach (['migrate-v2.sql', 'migrate-v3.sql', 'migrate-v4.sql'] as $file) {
                    $mig = file_get_contents(__DIR__ . '/database/' . $file);
                    if ($mig === false) {
                        continue;
                    }
                    foreach (preg_split('/;\s*\R/', $mig) ?: [] as $chunk) {
                        $chunk = trim($chunk);
                        if ($chunk === '' || str_starts_with($chunk, '--')) {
                            continue;
                        }
                        try {
                            $pdo->exec($chunk);
                        } catch (Throwable $ex) {
                            $messages[] = 'Atlandi (' . $file . '): ' . substr($ex->getMessage(), 0, 80);
                        }
                    }
                }
                foreach (['google_id VARCHAR(128) NULL', 'avatar_url VARCHAR(512) NULL'] as $col) {
                    try {
                        $pdo->exec('ALTER TABLE users ADD COLUMN ' . $col);
                    } catch (Throwable $ex) {
                        // column exists
                    }
                }
                try {
                    $pdo->exec('ALTER TABLE trade_listings ADD COLUMN attrs_json TEXT NULL AFTER photo_urls');
                } catch (Throwable $ex) {
                    // column exists
                }
                $messages[] = 'v2+v3 migration tamam (Google, mesajlar, attrs_json)';
            } elseif ($islem === 'googleconfig') {
                $clientId = trim((string) ($_POST['client_id'] ?? ''));
                $clientSecret = trim((string) ($_POST['client_secret'] ?? ''));
                if ($clientId === '' || $clientSecret === '') {
                    throw new RuntimeException('client_id ve client_secret gerekli');
                }
                if (!is_dir(__DIR__ . '/config')) {
                    mkdir(__DIR__ . '/config', 0755, true);
                }
                $php = "<?php\n"
                    . "declare(strict_types=1);\n\n"
                    . 'return ' . var_export([
                        'client_id' => $clientId,
                        'client_secret' => $clientSecret,
                    ], true) . ";\n";
                $target = __DIR__ . '/config/google.local.php';
                if (file_put_contents($target, $php) === false) {
                    throw new RuntimeException('google.local.php yazilamadi');
                }
                require_once __DIR__ . '/app/Services/GoogleAuthService.php';
                $gc = \App\Services\GoogleAuthService::config();
                $messages[] = 'google.local.php yazildi (' . strlen($php) . ' byte)';
                $messages[] = 'Google OAuth: ' . ($gc['enabled'] ? 'AKTIF' : 'PASIF');
                $ru = (string) ($gc['redirect_uri'] ?? '');
                $messages[] = 'Redirect URI (Console\'a AYNEN ekleyin): ' . $ru;
                $messages[] = 'JavaScript origin: ' . rtrim((string) (cx_app_config()['url'] ?? ''), '/');
                $messages[] = 'Hata redirect_uri_mismatch ise Console -> Web client -> Authorized redirect URIs';
            } elseif ($islem === 'deployhook') {
                if (!is_dir(__DIR__ . '/config')) {
                    mkdir(__DIR__ . '/config', 0755, true);
                }
                $secret = bin2hex(random_bytes(24));
                file_put_contents(
                    __DIR__ . '/config/deploy.local.php',
                    "<?php\nreturn ['secret' => " . var_export($secret, true) . "];\n"
                );
                $messages[] = 'Deploy aktif. Secret (bir kez kaydedin): ' . $secret;
                $messages[] = 'PC: python scripts/deploy_live_php.py';
            } else {
                $newPass = (string) ($_POST['superadmin_password'] ?? '');
                if (strlen($newPass) < 12) {
                    throw new RuntimeException('superadmin sifresi en az 12 karakter olmali.');
                }
                $schema = file_get_contents(__DIR__ . '/database/schema.sql');
                if ($schema === false) {
                    throw new RuntimeException('schema.sql bulunamadi');
                }
                foreach (preg_split('/;\s*\R/', $schema) ?: [] as $chunk) {
                    $chunk = trim($chunk);
                    if ($chunk === '' || strpos($chunk, '--') === 0) {
                        continue;
                    }
                    $pdo->exec($chunk);
                }
                $messages[] = 'Tablolar olusturuldu';
                $hash = App\Helpers\Auth::hashPassword($newPass);
                $pdo->prepare(
                    'INSERT INTO users (username, password_hash, role, created_at)
                     VALUES (?,?,?,?)
                     ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), role = VALUES(role)'
                )->execute(['superadmin', $hash, 'superadmin', microtime(true)]);
                $messages[] = 'superadmin olusturuldu — sifreyi guvenli yerde saklayin.';
                if (!is_dir(__DIR__ . '/storage/sessions')) {
                    mkdir(__DIR__ . '/storage/sessions', 0755, true);
                }
                if (!is_dir(__DIR__ . '/storage')) {
                    mkdir(__DIR__ . '/storage', 0755, true);
                }
                file_put_contents(__DIR__ . '/storage/installed.lock', date('c'));
                $messages[] = 'Kurulum tamam — bu dosyayi silin';
            }
        } catch (Throwable $e) {
            $messages[] = 'HATA: ' . $e->getMessage();
        }
    }
}
?>
<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <title>BenimBazar Kurulum</title>
  <style>
    body{font-family:sans-serif;max-width:520px;margin:40px auto;padding:20px}
    input,button{width:100%;padding:12px;margin:8px 0;font-size:16px}
    .msg{background:#f0f0f0;padding:12px;margin:12px 0;border-radius:8px}
  </style>
</head>
<body>
<h1>BenimBazar Kurulum</h1>
<p>403 aliyorsaniz install.php yerine bu sayfayi kullanin.</p>
<?php foreach ($messages as $m): ?>
  <div class="msg"><?= htmlspecialchars($m, ENT_QUOTES, 'UTF-8') ?></div>
<?php endforeach; ?>
<form method="post">
  <label>Kurulum anahtari (config/setup.local.php)</label>
  <input name="anahtar" type="password" required>
  <label>Superadmin sifresi (min 12 karakter)</label>
  <input name="superadmin_password" type="password" minlength="12" required autocomplete="new-password">
  <input type="hidden" name="islem" value="kur">
  <button type="submit">Tablolari olustur</button>
</form>
<form method="post">
  <input name="anahtar" type="password" required>
  <label>Yeni superadmin sifresi (min 12 karakter)</label>
  <input name="new_password" type="password" minlength="12" required autocomplete="new-password">
  <input type="hidden" name="islem" value="superpass">
  <button type="submit">Superadmin sifresini sifirla</button>
</form>
<form method="post">
  <input name="anahtar" type="password" required>
  <input type="hidden" name="islem" value="migrate">
  <button type="submit">v2 migration (Google + mesajlar)</button>
</form>
<form method="post">
  <input name="anahtar" type="password" required>
  <input type="hidden" name="islem" value="cargrseed">
  <button type="submit">Car.gr cesitli ilanlar (mevcut kullanicilara, ~62 adet)</button>
</form>
<form method="post">
  <input name="anahtar" type="password" required>
  <input type="hidden" name="islem" value="vehicleseed">
  <button type="submit">25 arac ilani + 5 kullanici yukle</button>
</form>
<form method="post">
  <input name="anahtar" type="password" required>
  <input type="hidden" name="islem" value="demo">
  <button type="submit">Ornek ilanlari yukle (7 adet + demo kullanici)</button>
</form>
<div class="msg" style="font-size:13px;line-height:1.5">
  <strong>Google redirect_uri_mismatch cozumu</strong><br>
  Console &rarr; OAuth client (Web) &rarr; Authorized redirect URIs:<br>
  <code>http://changex.mehmetfer.com.tr/auth/google-callback.php</code><br>
  JavaScript origins: <code>http://changex.mehmetfer.com.tr</code><br>
  Sadece domain (<code>/auth/google-callback.php</code> olmadan) calismaz.
</div>
<form method="post">
  <input name="anahtar" type="password" required>
  <label>Google Client ID</label>
  <input name="client_id" type="text" placeholder="xxx.apps.googleusercontent.com" value="591768912856-dkse8medesgjkojuc8bls7tdb4jtlooq.apps.googleusercontent.com">
  <label>Google Client Secret</label>
  <input name="client_secret" type="password" placeholder="GOCSPX-..." required>
  <input type="hidden" name="islem" value="googleconfig">
  <button type="submit">Google OAuth yapilandir (google.local.php)</button>
</form>
<form method="post">
  <input name="anahtar" type="password" required>
  <input type="hidden" name="islem" value="deployhook">
  <button type="submit">Otomatik deploy kur (HTTP hook)</button>
</form>
<p style="font-size:13px;color:#666">Deploy: once asagidaki butona basin. Sonra PC den otomatik yukleme calisir.</p>
<p><a href="/test.php">test.php</a> · <a href="/login.php">Giris</a> · <a href="/index.php">Ana sayfa</a></p>
</body>
</html>
