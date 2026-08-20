<?php
/** BenimBazar — FTP / deploy test (kurulumdan sonra silinebilir). */
declare(strict_types=1);

/** @var array<string,mixed> $cfg */
$cfg = require __DIR__ . '/config/app.php';
if (!empty($cfg['production'])) {
    http_response_code(404);
    exit;
}

header('Content-Type: text/html; charset=utf-8');
ini_set('display_errors', '1');
error_reporting(E_ALL);

$versionFile = __DIR__ . '/version.php';
$version = is_file($versionFile) ? (require $versionFile) : [];
$markerTime = (string) ($version['time'] ?? '—');
$markerTag = (string) ($version['tag'] ?? '—');

$checks = [];
$ok = static function (string $label, string $detail = 'OK') use (&$checks): void {
    $checks[] = ['ok' => true, 'label' => $label, 'detail' => $detail];
};
$fail = static function (string $label, string $detail) use (&$checks): void {
    $checks[] = ['ok' => false, 'label' => $label, 'detail' => $detail];
};

$ok('Sunucu', $_SERVER['SERVER_NAME'] ?? '—');
$ok('PHP', PHP_VERSION);
$ok('Bu dosya', 'test.php · ' . date('Y-m-d H:i:s', filemtime(__FILE__)));
$ok('Surum', $markerTag . ' · ' . $markerTime);

if (is_file(__DIR__ . '/assets/style.css')) {
    $ok('CSS', number_format((int) filesize(__DIR__ . '/assets/style.css')) . ' byte');
} else {
    $fail('CSS', 'assets/style.css yok');
}

$bootstrapOk = false;
try {
    require __DIR__ . '/bootstrap.php';
    cx_app_config();
    $bootstrapOk = true;
    $ok('bootstrap', 'OK');
} catch (Throwable $e) {
    $fail('bootstrap', $e->getMessage());
}

if ($bootstrapOk) {
    try {
        $cfg = cx_load_db_config();
        App\Helpers\Database::connect($cfg);
        App\Helpers\Database::pdo()->query('SELECT 1');
        $ok('MySQL', $cfg['database']);
        $n = (int) App\Helpers\Database::pdo()->query('SELECT COUNT(*) c FROM users')->fetch()['c'];
        $ok('users', (string) $n . ' kayit');
    } catch (Throwable $e) {
        $fail('MySQL', $e->getMessage());
    }
}

$allOk = $checks !== [] && !in_array(false, array_column($checks, 'ok'), true);

if (!empty($_GET['raw'])) {
    header('Content-Type: text/plain; charset=utf-8');
    echo "=== BenimBazar FTP TEST ===\n";
    echo "Surum: $markerTag\n";
    echo "Zaman: $markerTime\n\n";
    foreach ($checks as $c) {
        echo ($c['ok'] ? '[OK] ' : '[HATA] ') . $c['label'] . ': ' . $c['detail'] . "\n";
    }
    exit;
}
?>
<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FTP Test — BenimBazar</title>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800&display=swap" rel="stylesheet">
  <style>
    body{margin:0;background:#0d0f14;color:#f5f5f5;font-family:Montserrat,system-ui,sans-serif;padding:24px 16px}
    .wrap{max-width:640px;margin:0 auto}
    h1{font-size:1.35rem;margin:0 0 8px}
    .tag{display:inline-block;background:#1a2332;border:1px solid #d4af37;color:#d4af37;padding:4px 10px;border-radius:999px;font-size:.75rem;font-weight:700;margin-bottom:16px}
    .status{padding:16px;border-radius:12px;margin:16px 0;font-weight:700;text-align:center}
    .status--ok{background:#0f2a1a;border:1px solid #2ecc71;color:#2ecc71}
    .status--fail{background:#2a0f0f;border:1px solid #e74c3c;color:#e74c3c}
    table{width:100%;border-collapse:collapse;font-size:.9rem}
    td{padding:10px 8px;border-bottom:1px solid #222}
    .pill{display:inline-block;padding:2px 8px;border-radius:6px;font-size:.75rem;font-weight:700}
    .pill--ok{background:#1a3d2a;color:#2ecc71}
    .pill--fail{background:#3d1a1a;color:#e74c3c}
    .btn{display:inline-block;margin-top:20px;padding:12px 18px;border-radius:10px;background:#d4af37;color:#0d0f14;text-decoration:none;font-weight:700}
    .hint{margin-top:20px;font-size:.8rem;color:#888;line-height:1.6}
    code{background:#1a2332;padding:2px 6px;border-radius:4px}
  </style>
</head>
<body>
<div class="wrap">
  <div class="tag"><?= htmlspecialchars($markerTag, ENT_QUOTES, 'UTF-8') ?></div>
  <h1>FTP Deploy Test</h1>
  <p style="color:#aaa">Son yukleme: <strong><?= htmlspecialchars($markerTime, ENT_QUOTES, 'UTF-8') ?></strong></p>
  <div class="status <?= $allOk ? 'status--ok' : 'status--fail' ?>">
    <?= $allOk ? 'FTP CALISIYOR — dosyalar canli sunucuda' : 'KONTROL GEREKLI' ?>
  </div>
  <table>
    <?php foreach ($checks as $c): ?>
    <tr>
      <td><?= htmlspecialchars($c['label'], ENT_QUOTES, 'UTF-8') ?></td>
      <td>
        <span class="pill <?= $c['ok'] ? 'pill--ok' : 'pill--fail' ?>"><?= $c['ok'] ? 'OK' : 'HATA' ?></span>
        <?= htmlspecialchars($c['detail'], ENT_QUOTES, 'UTF-8') ?>
      </td>
    </tr>
    <?php endforeach; ?>
  </table>
  <a class="btn" href="/index.php">Ana Sayfaya Git</a>
  <p class="hint">
    FTP sonrasi bu sayfayi yenileyin; <strong>Surum / Zaman</strong> degismeli.<br>
    Ana sayfada yesil bant: <a href="/index.php" style="color:#d4af37">index.php</a><br>
    Duz metin: <a href="/test.php?raw=1" style="color:#d4af37">test.php?raw=1</a>
  </p>
</div>
</body>
</html>
