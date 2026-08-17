<?php
declare(strict_types=1);
/** @var array<string,mixed>|null $user */
/** @var string $title */
/** @var string $content */
/** @var string|null $mainContent listing sayfasi icin guvenli govde (ogMeta dongusu $content ezmesin) */
/** @var string $layout layout: app|auth|plain */
/** @var string $bodyClass */
/** @var array<string,string>|null $ogMeta */
$app = cx_app_config();
$user = $user ?? cx_current_user();
$navNotifyCount = 0;
if ($user) {
    $cacheKey = 'cx_notify_count';
    $cacheTs = 'cx_notify_count_ts';
    $cached = \App\Helpers\Session::get($cacheKey);
    $cachedTs = (int) \App\Helpers\Session::get($cacheTs, 0);
    if (is_int($cached) && (time() - $cachedTs) < 60) {
        $navNotifyCount = $cached;
    } else {
        try {
            require_once BASE_PATH . '/app/Services/NotificationService.php';
            $navNotifyCount = (new \App\Services\NotificationService())->unreadCount((int) $user['id']);
            \App\Helpers\Session::set($cacheKey, $navNotifyCount);
            \App\Helpers\Session::set($cacheTs, time());
        } catch (Throwable) {
            $navNotifyCount = 0;
        }
    }
}
$layout = $layout ?? 'app';
$navActive = $navActive ?? 'home';
$bodyClass = $bodyClass ?? '';
?>
<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= cx_e($title) ?> — <?= cx_e(cx_site_name()) ?></title>
  <script>
  (function () {
    try {
      var t = localStorage.getItem('cx_theme');
      if (t !== 'light' && t !== 'dark') t = 'light';
      document.documentElement.setAttribute('data-theme', t);
    } catch (e) {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  })();
  </script>
  <?php
    $favicon = cx_brand_asset_path('favicon');
    $favicon32 = cx_brand_asset_path('favicon_32') ?: $favicon;
    if ($favicon !== ''):
  ?>
  <link rel="icon" href="<?= cx_e($favicon32) ?>" type="image/png" sizes="32x32">
  <link rel="icon" href="<?= cx_e($favicon) ?>" type="image/png" sizes="512x512">
  <link rel="apple-touch-icon" href="<?= cx_e($favicon) ?>">
  <?php endif; ?>
  <?php if (!empty($ogMeta) && is_array($ogMeta)): ?>
    <?php foreach ($ogMeta as $property => $ogValue): ?>
      <?php if ($ogValue === '') { continue; } ?>
      <?php if (str_starts_with($property, 'twitter:')): ?>
      <meta name="<?= cx_e($property) ?>" content="<?= cx_e($ogValue) ?>">
      <?php else: ?>
      <meta property="<?= cx_e($property) ?>" content="<?= cx_e($ogValue) ?>">
      <?php endif; ?>
    <?php endforeach; ?>
  <?php endif; ?>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/style.css?v=20260816theme2">
  <style>
    body{margin:0;background:var(--bg);color:var(--ink);font-family:Montserrat,system-ui,sans-serif}
    a{color:var(--gold)}
  </style>
</head>
<body class="<?= cx_e(trim($bodyClass)) ?>">
<button type="button" class="cx-theme-toggle" id="cx-theme-toggle" data-theme-state="light" aria-label="Karanlık moda geç" title="Karanlık mod">
  <svg data-icon="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4"/>
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
  </svg>
  <svg data-icon="moon" hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
    <path d="M21 14.5A8.5 8.5 0 1 1 9.5 3 7 7 0 0 0 21 14.5z"/>
  </svg>
</button>
<?php if ($layout === 'auth'): ?>
<div class="auth-shell">
  <div class="auth-card">
    <?php if ($msg = cx_flash('error')): ?><div class="alert alert-error"><?= cx_e($msg) ?></div><?php endif; ?>
    <?php if ($msg = cx_flash('ok')): ?><div class="alert alert-ok"><?= cx_e($msg) ?></div><?php endif; ?>
    <?= $mainContent ?? $content ?>
  </div>
</div>
<?php else: ?>
<div class="app-shell<?= $layout === 'admin' ? ' app-shell--admin' : '' ?>">
  <main class="app-main<?= $layout === 'admin' ? ' app-main--admin' : '' ?>">
    <?php if ($msg = cx_flash('error')): ?><div class="alert alert-error"><?= cx_e($msg) ?></div><?php endif; ?>
    <?php if ($msg = cx_flash('ok')): ?><div class="alert alert-ok"><?= cx_e($msg) ?></div><?php endif; ?>
    <?= $mainContent ?? $content ?>
  </main>
  <?php if ($layout === 'app'): ?>
    <?php require __DIR__ . '/partials/site-legal-footer.php'; ?>
    <?php require __DIR__ . '/partials/bottom-nav.php'; ?>
  <?php endif; ?>
</div>
<?php endif; ?>
<script src="/assets/theme-toggle.js?v=1" defer></script>
</body>
</html>
