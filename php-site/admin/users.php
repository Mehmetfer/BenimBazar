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

if (!cx_is_admin($user)) {
    cx_flash('error', 'Kullanıcı listesi yalnızca yönetici / superadmin içindir.');
    cx_redirect('/admin/');
}

ListingSchemaService::ensureUserColumns();

$q = trim((string) ($_GET['q'] ?? ''));
$canAssignRoles = cx_is_superadmin($user);

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    if (!$canAssignRoles) {
        cx_flash('error', 'Rol / VIP üyelik tarihi yalnızca superadmin içindir.');
        cx_redirect('/admin/users.php?q=' . urlencode($q));
    }
    Security::rateLimit('admin_assign_role', 30, 300);
    $targetId = (int) ($_POST['user_id'] ?? 0);
    $action = (string) ($_POST['action'] ?? 'assign_role');
    try {
        if ($action === 'vip_dates') {
            UserAdminService::updateVipMembershipDates(
                $targetId,
                (string) ($_POST['vip_starts_at'] ?? ''),
                (string) ($_POST['vip_ends_at'] ?? ''),
                (int) $user['id']
            );
            cx_flash('ok', 'VIP üyelik tarihleri güncellendi.');
        } else {
            $role = (string) ($_POST['role'] ?? '');
            UserAdminService::assignRole(
                $targetId,
                $role,
                (int) $user['id'],
                (string) ($_POST['vip_starts_at'] ?? ''),
                (string) ($_POST['vip_ends_at'] ?? '')
            );
            cx_flash('ok', 'Rol guncellendi: ' . UserAdminService::label($role));
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    cx_redirect('/admin/users.php?q=' . urlencode($q));
}

$rows = UserAdminService::search($q);
$labels = UserAdminService::roleLabels();
$assignable = UserAdminService::ASSIGNABLE;

ob_start();
$adminTab = 'users';
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<p class="admin-list-meta">
  Kullanıcıların yayınladığı ilan sayılarını görün; sayıya tıklayınca o kullanıcının ilanlarını yönetin
  (düzenle, onayla, beklet, reddet<?= cx_can_cancel_listings($user) ? ', sil' : '' ?>).
  <?php if ($canAssignRoles): ?>
  Superadmin ayrıca rol atayabilir; başlangıç/bitiş tarihi yalnızca VIP Kurumsal için görünür.
  <?php endif; ?>
</p>

<form class="admin-toolbar" method="get">
  <input class="admin-toolbar__search" type="search" name="q" value="<?= cx_e($q) ?>" placeholder="Kullanıcı adı veya e-posta">
  <button class="admin-toolbar__btn" type="submit">Ara</button>
</form>

<div class="admin-users-table-wrap">
<table class="admin-table admin-table--users">
  <thead>
    <tr>
      <th>ID</th>
      <th>Ülke</th>
      <th>Kullanici</th>
      <th>Mevcut rol</th>
      <th>İlanlar</th>
      <th>Change Score</th>
      <?php if ($canAssignRoles): ?><th>Yeni rol</th><?php endif; ?>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($rows as $r):
    $rid = (int) $r['id'];
    $current = (string) ($r['role'] ?? 'user');
    $protected = $current === 'superadmin';
    $country = cx_normalize_country((string) ($r['country'] ?? 'tr'));
    $total = (int) ($r['listing_total'] ?? 0);
    $published = (int) ($r['listing_published'] ?? 0);
    $pending = (int) ($r['listing_pending'] ?? 0);
    $vipSummary = cx_vip_membership_summary($r);
    $isVip = $current === 'vip_kurumsal';
  ?>
    <tr>
      <td><?= $rid ?></td>
      <td>
        <?php require dirname(__DIR__) . '/views/partials/user-country-flag.php'; ?>
      </td>
      <td>
        <strong><?= cx_e($r['username']) ?></strong>
        <?php if (!empty($r['email'])): ?><br><span style="color:var(--muted);font-size:11px"><?= cx_e($r['email']) ?></span><?php endif; ?>
        <?php if (!empty($r['phone'])): ?><br><span style="color:var(--muted);font-size:11px">📱 <?= cx_e($r['phone']) ?></span><?php endif; ?>
        <?php if (!empty($r['city'])): ?><br><span style="color:var(--muted);font-size:11px">📍 <?= cx_e($r['city']) ?></span><?php endif; ?>
        <?php if ($isVip): ?>
        <div class="admin-users__vip-meta<?= $vipSummary['expired'] ? ' is-expired' : '' ?>">
          VIP:
          <?= $vipSummary['starts'] !== '' ? cx_e($vipSummary['starts']) : '—' ?>
          →
          <?= $vipSummary['ends'] !== '' ? cx_e($vipSummary['ends']) : '—' ?>
          <span>(<?= cx_e($vipSummary['status_label']) ?>)</span>
        </div>
        <?php endif; ?>
      </td>
      <td><?= cx_e($labels[$current] ?? $current) ?></td>
      <td class="admin-users__listings">
        <a class="admin-users__listing-link" href="/admin/user-listings.php?id=<?= $rid ?>">
          <strong><?= $total ?></strong>
          <span>toplam</span>
        </a>
        <?php if ($total > 0): ?>
        <div class="admin-users__listing-breakdown">
          <a href="/admin/user-listings.php?id=<?= $rid ?>&amp;status=approved"><?= $published ?> yayında</a>
          ·
          <a href="/admin/user-listings.php?id=<?= $rid ?>&amp;status=pending"><?= $pending ?> bekleyen</a>
        </div>
        <?php else: ?>
        <div class="admin-users__listing-breakdown muted">İlan yok</div>
        <?php endif; ?>
      </td>
      <td><?= (int) ($r['change_score'] ?? 0) ?></td>
      <?php if ($canAssignRoles): ?>
      <td>
        <?php if ($protected): ?>
          <em>Superadmin — degistirilemez</em>
        <?php else: ?>
        <form method="post" class="role-form<?= $isVip ? ' role-form--vip' : '' ?>" data-role-form>
          <?= cx_csrf_field() ?>
          <input type="hidden" name="action" value="assign_role">
          <input type="hidden" name="user_id" value="<?= $rid ?>">
          <select name="role" class="role-form__role" data-role-select>
            <?php foreach ($assignable as $roleKey): ?>
            <option value="<?= cx_e($roleKey) ?>"<?= $current === $roleKey ? ' selected' : '' ?>>
              <?= cx_e($labels[$roleKey] ?? $roleKey) ?>
            </option>
            <?php endforeach; ?>
          </select>
          <?php if ($isVip): ?>
          <div class="role-form__vip-dates" data-vip-dates>
            <label>
              <span>Başlangıç</span>
              <input type="date" name="vip_starts_at" value="<?= cx_e($vipSummary['starts_ymd']) ?>" required>
            </label>
            <label>
              <span>Bitiş</span>
              <input type="date" name="vip_ends_at" value="<?= cx_e($vipSummary['ends_ymd']) ?>" required>
            </label>
          </div>
          <p class="role-form__hint" data-vip-hint>VIP Kurumsal üyelik süresi — yalnızca bu rolde.</p>
          <?php else: ?>
          <div class="role-form__vip-dates" data-vip-dates hidden>
            <label>
              <span>Başlangıç</span>
              <input type="date" name="vip_starts_at" value="" disabled>
            </label>
            <label>
              <span>Bitiş</span>
              <input type="date" name="vip_ends_at" value="" disabled>
            </label>
          </div>
          <p class="role-form__hint" data-vip-hint hidden>VIP Kurumsal seçerseniz başlangıç / bitiş tarihi girin.</p>
          <?php endif; ?>
          <button class="btn" type="submit">Kaydet</button>
        </form>
        <?php endif; ?>
      </td>
      <?php endif; ?>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>

<p class="admin-list-meta">
  <strong>Roller:</strong> Onaycı → ilan onay/düzenle · Yönetici → silme dahil tam yetki · Üye → normal
  · Başlangıç/bitiş tarihi yalnızca VIP Kurumsal hesaplarda; sadece superadmin görür ve değiştirir.
</p>
<script>
(function () {
  function syncVipDates(form) {
    var select = form.querySelector('[data-role-select]');
    var dates = form.querySelector('[data-vip-dates]');
    var hint = form.querySelector('[data-vip-hint]');
    if (!select || !dates) return;
    var isVip = select.value === 'vip_kurumsal';
    form.classList.toggle('role-form--vip', isVip);
    dates.hidden = !isVip;
    dates.querySelectorAll('input').forEach(function (input) {
      input.disabled = !isVip;
      if (isVip) {
        input.required = true;
      } else {
        input.required = false;
        input.value = '';
      }
    });
    if (hint) hint.hidden = !isVip;
  }
  document.querySelectorAll('[data-role-form]').forEach(function (form) {
    var select = form.querySelector('[data-role-select]');
    if (!select) return;
    select.addEventListener('change', function () { syncVipDates(form); });
    syncVipDates(form);
  });
})();
</script>
<?php
$content = ob_get_clean();
$title = 'Kullanıcılar';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
