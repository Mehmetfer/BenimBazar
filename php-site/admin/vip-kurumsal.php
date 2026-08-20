<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/UserAdminService.php';
require_once dirname(__DIR__) . '/app/Services/ListingSchemaService.php';

use App\Helpers\Security;
use App\Services\ListingSchemaService;
use App\Services\UserAdminService;

cx_bootstrap();
$user = cx_require_user();

if (!cx_is_superadmin($user)) {
    cx_flash('error', 'VIP Kurumsal yönetimi yalnızca superadmin içindir.');
    cx_redirect('/admin/');
}

ListingSchemaService::ensureUserColumns();

$q = trim((string) ($_GET['q'] ?? ''));
$filter = strtolower(trim((string) ($_GET['filter'] ?? 'all')));
$allowedFilters = ['all', 'active', 'expiring', 'expired', 'upcoming', 'nodates'];
if (!in_array($filter, $allowedFilters, true)) {
    $filter = 'all';
}

$redirectParams = static function () use ($q, $filter): string {
    return http_build_query(array_filter([
        'q' => $q !== '' ? $q : null,
        'filter' => $filter !== 'all' ? $filter : null,
    ]));
};

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    Security::rateLimit('admin_vip_kurumsal', 40, 300);
    $targetId = (int) ($_POST['user_id'] ?? 0);
    $action = (string) ($_POST['action'] ?? '');

    try {
        if ($action === 'vip_dates') {
            UserAdminService::updateVipMembershipDates(
                $targetId,
                (string) ($_POST['vip_starts_at'] ?? ''),
                (string) ($_POST['vip_ends_at'] ?? ''),
                (int) $user['id']
            );
            cx_flash('ok', 'VIP üyelik tarihleri güncellendi.');
        } elseif ($action === 'extend') {
            $days = (int) ($_POST['extend_days'] ?? 0);
            UserAdminService::extendVipMembership($targetId, $days, (int) $user['id']);
            cx_flash('ok', 'VIP üyelik ' . $days . ' gün uzatıldı.');
        } elseif ($action === 'promote') {
            UserAdminService::assignRole(
                $targetId,
                'vip_kurumsal',
                (int) $user['id'],
                (string) ($_POST['vip_starts_at'] ?? ''),
                (string) ($_POST['vip_ends_at'] ?? '')
            );
            cx_flash('ok', 'Kullanıcı VIP Kurumsal yapıldı.');
        } elseif ($action === 'downgrade') {
            $toRole = (string) ($_POST['downgrade_role'] ?? 'dealer');
            if (!in_array($toRole, ['user', 'dealer'], true)) {
                throw new RuntimeException('Geçersiz hedef rol.');
            }
            UserAdminService::assignRole($targetId, $toRole, (int) $user['id']);
            cx_flash('ok', 'VIP kaldırıldı: ' . UserAdminService::label($toRole));
        } else {
            throw new RuntimeException('Geçersiz işlem.');
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }

    cx_redirect('/admin/vip-kurumsal.php?' . $redirectParams());
}

$stats = UserAdminService::vipMembershipStats();
$rows = UserAdminService::searchVipKurumsal($q, $filter);
$promoteQ = trim((string) ($_GET['promote_q'] ?? ''));
$promoteHits = $promoteQ !== '' ? UserAdminService::searchPromotable($promoteQ) : [];
$labels = UserAdminService::roleLabels();
$app = cx_app_config();
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');

ob_start();
$adminTab = 'vip';
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<p class="admin-list-meta">
  VIP Kurumsal galerilerin üyelik süresi, galeri profili ve ilanlarını buradan yönetin.
  Genel kullanıcı listesinden ayrı tutulur.
</p>

<div class="admin-vip-stats" aria-label="VIP özet">
  <a class="admin-vip-stat<?= $filter === 'all' ? ' is-active' : '' ?>" href="/admin/vip-kurumsal.php">
    <strong><?= (int) $stats['total'] ?></strong><span>Toplam VIP</span>
  </a>
  <a class="admin-vip-stat<?= $filter === 'active' ? ' is-active' : '' ?>" href="/admin/vip-kurumsal.php?filter=active">
    <strong><?= (int) $stats['active'] ?></strong><span>Aktif</span>
  </a>
  <a class="admin-vip-stat admin-vip-stat--warn<?= $filter === 'expiring' ? ' is-active' : '' ?>" href="/admin/vip-kurumsal.php?filter=expiring">
    <strong><?= (int) $stats['expiring'] ?></strong><span>30 gün içinde biten</span>
  </a>
  <a class="admin-vip-stat admin-vip-stat--danger<?= $filter === 'expired' ? ' is-active' : '' ?>" href="/admin/vip-kurumsal.php?filter=expired">
    <strong><?= (int) $stats['expired'] ?></strong><span>Süresi dolmuş</span>
  </a>
  <a class="admin-vip-stat<?= $filter === 'upcoming' ? ' is-active' : '' ?>" href="/admin/vip-kurumsal.php?filter=upcoming">
    <strong><?= (int) $stats['upcoming'] ?></strong><span>Henüz başlamamış</span>
  </a>
  <a class="admin-vip-stat<?= $filter === 'nodates' ? ' is-active' : '' ?>" href="/admin/vip-kurumsal.php?filter=nodates">
    <strong><?= (int) $stats['nodates'] ?></strong><span>Tarih tanımsız</span>
  </a>
</div>

<form class="admin-toolbar" method="get">
  <?php if ($filter !== 'all'): ?>
  <input type="hidden" name="filter" value="<?= cx_e($filter) ?>">
  <?php endif; ?>
  <input class="admin-toolbar__search" type="search" name="q" value="<?= cx_e($q) ?>" placeholder="Galeri adı, kullanıcı, e-posta, şehir">
  <button class="admin-toolbar__btn" type="submit">Ara</button>
</form>

<section class="admin-vip-promote" aria-label="VIP yap">
  <h2 class="admin-vip-section-title">Üye / galeriyi VIP Kurumsal yap</h2>
  <form class="admin-toolbar" method="get">
    <?php if ($filter !== 'all'): ?>
    <input type="hidden" name="filter" value="<?= cx_e($filter) ?>">
    <?php endif; ?>
    <?php if ($q !== ''): ?>
    <input type="hidden" name="q" value="<?= cx_e($q) ?>">
    <?php endif; ?>
    <input class="admin-toolbar__search" type="search" name="promote_q" value="<?= cx_e($promoteQ) ?>" placeholder="Kullanıcı veya galeri ara (üye / kurumsal)">
    <button class="admin-toolbar__btn" type="submit">Bul</button>
  </form>
  <?php if ($promoteQ !== '' && $promoteHits === []): ?>
  <p class="admin-list-meta">“<?= cx_e($promoteQ) ?>” için uygun üye bulunamadı.</p>
  <?php elseif ($promoteHits !== []): ?>
  <div class="admin-vip-promote-list">
    <?php foreach ($promoteHits as $hit):
        $hid = (int) ($hit['id'] ?? 0);
        $defaultStart = date('Y-m-d');
        $defaultEnd = date('Y-m-d', strtotime('+1 year'));
    ?>
    <article class="admin-vip-promote-card">
      <div>
        <strong><?= cx_e((string) ($hit['gallery_name'] ?? $hit['username'] ?? '')) ?></strong>
        <span class="muted">@<?= cx_e((string) ($hit['username'] ?? '')) ?> · <?= cx_e($labels[(string) ($hit['role'] ?? 'user')] ?? '') ?></span>
      </div>
      <form method="post" class="admin-vip-promote-form">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="action" value="promote">
        <input type="hidden" name="user_id" value="<?= $hid ?>">
        <label><span>Başlangıç</span><input type="date" name="vip_starts_at" value="<?= cx_e($defaultStart) ?>" required></label>
        <label><span>Bitiş</span><input type="date" name="vip_ends_at" value="<?= cx_e($defaultEnd) ?>" required></label>
        <button class="btn btn-sm" type="submit">VIP yap</button>
      </form>
    </article>
    <?php endforeach; ?>
  </div>
  <?php endif; ?>
</section>

<?php if ($rows === []): ?>
<p class="empty-state">Bu filtrede VIP Kurumsal hesap yok.</p>
<?php else: ?>
<div class="admin-vip-list">
  <?php foreach ($rows as $r):
      $rid = (int) ($r['id'] ?? 0);
      $vipSummary = cx_vip_membership_summary($r);
      $galleryName = trim((string) ($r['gallery_name'] ?? ''));
      $displayName = $galleryName !== '' ? $galleryName : (string) ($r['username'] ?? '');
      $logoSrc = cx_user_avatar_src((string) ($r['avatar_url'] ?? ''), $uploadsUrl);
      $total = (int) ($r['listing_total'] ?? 0);
      $published = (int) ($r['listing_published'] ?? 0);
      $pending = (int) ($r['listing_pending'] ?? 0);
      $cardClass = 'admin-vip-card';
      if ($vipSummary['expired']) {
          $cardClass .= ' is-expired';
      } elseif ($vipSummary['active']) {
          $cardClass .= ' is-active';
      }
  ?>
  <article class="<?= cx_e($cardClass) ?>">
    <header class="admin-vip-card__head">
      <div class="admin-vip-card__identity">
        <div class="admin-vip-card__logo<?= $logoSrc === '' ? ' admin-vip-card__logo--empty' : '' ?>">
          <?php if ($logoSrc !== ''): ?>
            <img src="<?= cx_e($logoSrc) ?>" alt="" width="48" height="48" loading="lazy">
          <?php else: ?>
            <span>VIP</span>
          <?php endif; ?>
        </div>
        <div>
          <h3 class="admin-vip-card__title"><?= cx_e($displayName) ?></h3>
          <p class="admin-vip-card__meta">
            #<?= $rid ?> · @<?= cx_e((string) ($r['username'] ?? '')) ?>
            <?php if (!empty($r['city'])): ?> · <?= cx_e((string) $r['city']) ?><?php endif; ?>
          </p>
          <p class="admin-vip-card__status<?= $vipSummary['expired'] ? ' is-expired' : '' ?>">
            <?= cx_e($vipSummary['status_label']) ?>
            <?php if ($vipSummary['has_dates']): ?>
              · <?= cx_e($vipSummary['starts']) ?> → <?= cx_e($vipSummary['ends']) ?>
            <?php endif; ?>
          </p>
        </div>
      </div>
      <div class="admin-vip-card__quick">
        <a class="btn-sm" href="/galeri.php?id=<?= $rid ?>" target="_blank" rel="noopener">Galeri</a>
        <a class="btn-sm" href="/admin/user-listings.php?id=<?= $rid ?>">İlanlar (<?= $total ?>)</a>
      </div>
    </header>

    <div class="admin-vip-card__stats">
      <span><strong><?= $published ?></strong> yayında</span>
      <span><strong><?= $pending ?></strong> bekleyen</span>
      <span>Change Score <strong><?= (int) ($r['change_score'] ?? 0) ?></strong></span>
    </div>

    <form method="post" class="admin-vip-card__dates">
      <?= cx_csrf_field() ?>
      <input type="hidden" name="action" value="vip_dates">
      <input type="hidden" name="user_id" value="<?= $rid ?>">
      <label>
        <span>Başlangıç</span>
        <input type="date" name="vip_starts_at" value="<?= cx_e($vipSummary['starts_ymd']) ?>" required>
      </label>
      <label>
        <span>Bitiş</span>
        <input type="date" name="vip_ends_at" value="<?= cx_e($vipSummary['ends_ymd']) ?>" required>
      </label>
      <button class="btn" type="submit">Tarihleri kaydet</button>
    </form>

    <div class="admin-vip-card__actions">
      <?php foreach ([30, 90, 365] as $extendDays): ?>
      <form method="post">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="action" value="extend">
        <input type="hidden" name="user_id" value="<?= $rid ?>">
        <input type="hidden" name="extend_days" value="<?= $extendDays ?>">
        <button class="btn-sm btn-sm--gold" type="submit">+<?= $extendDays ?> gün</button>
      </form>
      <?php endforeach; ?>

      <form method="post" class="admin-vip-card__downgrade" onsubmit="return confirm('VIP kaldırılsın mı?');">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="action" value="downgrade">
        <input type="hidden" name="user_id" value="<?= $rid ?>">
        <select name="downgrade_role">
          <option value="dealer">Kurumsal (Galeri)</option>
          <option value="user">Üye</option>
        </select>
        <button class="btn-sm btn-sm--danger" type="submit">VIP kaldır</button>
      </form>
    </div>
  </article>
  <?php endforeach; ?>
</div>
<?php endif; ?>

<p class="admin-list-meta">
  <a class="link-gold" href="/admin/users.php">← Tüm kullanıcılar</a>
  · Süresi dolan VIP hesaplar giriş yapamaz · Tarih tanımsız hesaplar giriş yapabilir (yönetim tanımlayana kadar).
</p>
<?php
$content = ob_get_clean();
$title = 'VIP Kurumsal';
$layout = 'admin';
$bodyClass = 'page-admin page-admin-vip';
require dirname(__DIR__) . '/views/layout.php';
