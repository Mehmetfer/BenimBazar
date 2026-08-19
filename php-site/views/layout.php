<?php
declare(strict_types=1);
/** @var array<string,mixed>|null $user */
/** @var string $title */
/** @var string $content */
/** @var string|null $mainContent listing sayfasi icin guvenli govde (ogMeta dongusu $content ezmesin) */
/** @var string $layout layout: app|auth|plain */
/** @var string $bodyClass */
/** @var string|null $metaDescription */
/** @var string|null $canonicalUrl */
/** @var string|null $jsonLd */
/** @var array<string,string>|null $ogMeta */
/** @var string|null $metaRobots */
/** @var bool|null $titleStandalone */
$metaDescription = $metaDescription ?? null;
$canonicalUrl = $canonicalUrl ?? null;
$jsonLd = $jsonLd ?? null;
$metaRobots = $metaRobots ?? cx_seo_auto_noindex();
$titleStandalone = !empty($titleStandalone);
$app = cx_app_config();
$user = $user ?? cx_current_user();
$navNotifyCount = 0;
$navMsgCount = 0;
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
    if (cx_messages_enabled()) {
        $msgCacheKey = 'cx_msg_count';
        $msgCacheTs = 'cx_msg_count_ts';
        $msgCached = \App\Helpers\Session::get($msgCacheKey);
        $msgCachedTs = (int) \App\Helpers\Session::get($msgCacheTs, 0);
        if (is_int($msgCached) && (time() - $msgCachedTs) < 60) {
            $navMsgCount = $msgCached;
        } else {
            try {
                require_once BASE_PATH . '/app/Services/MessageService.php';
                $navMsgCount = (new \App\Services\MessageService())->unreadCount((int) $user['id']);
                \App\Helpers\Session::set($msgCacheKey, $navMsgCount);
                \App\Helpers\Session::set($msgCacheTs, time());
            } catch (Throwable) {
                $navMsgCount = 0;
            }
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
  <title><?= cx_e($titleStandalone ? $title : ($title . ' — ' . cx_site_name())) ?></title>
  <?php if (!empty($metaDescription)): ?>
  <meta name="description" content="<?= cx_e($metaDescription) ?>">
  <?php endif; ?>
  <?php if (!empty($metaRobots)): ?>
  <meta name="robots" content="<?= cx_e($metaRobots) ?>">
  <?php endif; ?>
  <?php foreach (cx_seo_verification_metas() as $verify): ?>
  <meta name="<?= cx_e($verify['name']) ?>" content="<?= cx_e($verify['content']) ?>">
  <?php endforeach; ?>
  <?php if (!empty($canonicalUrl)): ?>
  <link rel="canonical" href="<?= cx_e($canonicalUrl) ?>">
  <?php endif; ?>
  <?php if (!empty($jsonLd)): ?>
  <script type="application/ld+json"><?= $jsonLd ?></script>
  <?php endif; ?>
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
  <link rel="stylesheet" href="/assets/style.css?v=20260819splash">
  <style>
    body{margin:0;background:var(--bg);color:var(--ink);font-family:Montserrat,system-ui,sans-serif}
    a{color:var(--gold)}
  </style>
</head>
<body class="<?= cx_e(trim($bodyClass)) ?>">
<div id="cx-splash" class="cx-splash" aria-hidden="true">
  <img class="cx-splash__logo" src="/assets/branding/logo-splash.png" alt="">
</div>
<script>
(function(){
  var splash = document.getElementById('cx-splash');
  if (!splash) { return; }
  var key = 'cx_splash_seen';
  try {
    if (sessionStorage.getItem(key)) {
      splash.style.display = 'none';
      return;
    }
    sessionStorage.setItem(key, '1');
  } catch(e) {}
  splash.classList.add('is-visible');
  setTimeout(function () {
    splash.classList.add('is-done');
    setTimeout(function () { splash.style.display = 'none'; }, 500);
  }, 1800);
})();
</script>
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
