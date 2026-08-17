<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/AdminListingService.php';

use App\Helpers\Security;
use App\Services\AdminListingService;

cx_bootstrap();
$user = cx_require_staff();
if (!cx_can_moderate_listings($user)) {
    cx_redirect('/admin/');
}

try {
    $svc = new AdminListingService();
    $rows = $svc->topViewed(30);
    $adminTab = 'topviews';

    ob_start();
    require dirname(__DIR__) . '/views/partials/admin-shell.php';
?>
<h1 class="admin-h1">En cok goruntulenen ilanlar</h1>
<p class="admin-lead">Son 30 ilan — goruntulenme sayisina gore.</p>

<?php if ($rows === []): ?>
  <div class="admin-empty">Veri yok.</div>
<?php else: ?>
  <div class="admin-list">
    <?php foreach ($rows as $r): ?>
      <article class="admin-row">
        <div class="admin-row__body">
          <h2 class="admin-row__title">
            <a href="/admin/listing-edit.php?id=<?= (int) $r['id'] ?>"><?= cx_e($r['title']) ?></a>
          </h2>
          <p class="admin-row__meta">
            #<?= (int) ($r['listing_no'] ?? 0) ?> · @<?= cx_e($r['owner_username']) ?>
            · 👁 <?= (int) ($r['view_count'] ?? 0) ?>
            · ❤️ <?= (int) ($r['favorite_count'] ?? 0) ?>
            · 💬 <?= (int) ($r['message_count'] ?? 0) ?>
            · <?= cx_e(cx_listing_status_label((string) ($r['status'] ?? ''))) ?>
          </p>
        </div>
      </article>
    <?php endforeach; ?>
  </div>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Goruntulenme raporu';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
} catch (Throwable $e) {
    \App\Helpers\ErrorHandler::handleException($e);
}
