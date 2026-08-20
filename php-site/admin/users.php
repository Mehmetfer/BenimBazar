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

$userAssignable = array_values(array_filter(

    UserAdminService::ASSIGNABLE,

    static fn (string $role): bool => $role !== 'vip_kurumsal'

));



if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();

    $action = (string) ($_POST['action'] ?? 'assign_role');

    if ($action === 'delete_user') {
        if (!$canAssignRoles) {
            cx_flash('error', 'Üye silme yalnızca superadmin içindir.');
            cx_redirect('/admin/users.php?q=' . urlencode($q));
        }
        Security::rateLimit('admin_delete_user', 20, 300);
        $targetId = (int) ($_POST['user_id'] ?? 0);
        try {
            $result = UserAdminService::deleteUser($targetId, (int) $user['id']);
            $msg = 'Üye silindi: ' . $result['username'];
            if ($result['listings_deleted'] > 0) {
                $msg .= ' (' . $result['listings_deleted'] . ' ilan kaldırıldı)';
            }
            cx_flash('ok', $msg);
        } catch (Throwable $e) {
            cx_flash('error', $e->getMessage());
        }
        cx_redirect('/admin/users.php?q=' . urlencode($q));
    }

    if (!$canAssignRoles) {

        cx_flash('error', 'Rol atama yalnızca superadmin içindir.');

        cx_redirect('/admin/users.php?q=' . urlencode($q));

    }

    Security::rateLimit('admin_assign_role', 30, 300);

    $targetId = (int) ($_POST['user_id'] ?? 0);

    $role = (string) ($_POST['role'] ?? '');

    try {

        if ($role === 'vip_kurumsal') {

            cx_flash('error', 'VIP Kurumsal ataması için VIP Kurumsal yönetim sayfasını kullanın.');

            cx_redirect('/admin/vip-kurumsal.php?promote_q=' . urlencode((string) ($_POST['username_hint'] ?? '')));

        }

        UserAdminService::assignRole($targetId, $role, (int) $user['id']);

        cx_flash('ok', 'Rol guncellendi: ' . UserAdminService::label($role));

    } catch (Throwable $e) {

        cx_flash('error', $e->getMessage());

    }

    cx_redirect('/admin/users.php?q=' . urlencode($q));

}



$rows = UserAdminService::search($q);

$labels = UserAdminService::roleLabels();



ob_start();

$adminTab = 'users';

?>

<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>



<p class="admin-list-meta">

  Kullanıcıların ilan sayılarını görün; sayıya tıklayınca ilanlarını yönetin.

  <?php if ($canAssignRoles): ?>

  <strong>VIP Kurumsal</strong> üyelikleri

  <a class="link-gold" href="/admin/vip-kurumsal.php">VIP Kurumsal</a> sekmesinden yönetilir.

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

      <?php if ($canAssignRoles): ?><th>İşlem</th><?php endif; ?>

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

    $isVip = $current === 'vip_kurumsal';

    $vipSummary = $isVip ? cx_vip_membership_summary($r) : null;

    $isSuspended = !empty($r['suspended']);
    $rowClass = trim(($isVip ? 'admin-users__row--vip' : '') . ' ' . ($isSuspended ? 'admin-users__row--suspended' : ''));

  ?>

    <tr<?= $rowClass !== '' ? ' class="' . cx_e($rowClass) . '"' : '' ?>>

      <td><?= $rid ?></td>

      <td>

        <?php require dirname(__DIR__) . '/views/partials/user-country-flag.php'; ?>

      </td>

      <td>

        <strong><?= cx_e($r['username']) ?></strong>
        <?php if ($isSuspended): ?>
        <span class="admin-users__suspended-badge">Askida</span>
        <?php endif; ?>

        <?php if (!empty($r['email'])): ?><br><span style="color:var(--muted);font-size:11px"><?= cx_e($r['email']) ?></span><?php endif; ?>

        <?php if (!empty($r['phone'])): ?><br><span style="color:var(--muted);font-size:11px">📱 <?= cx_e($r['phone']) ?></span><?php endif; ?>

        <?php if (!empty($r['city'])): ?><br><span style="color:var(--muted);font-size:11px">📍 <?= cx_e($r['city']) ?></span><?php endif; ?>

        <?php if ($isVip && $vipSummary): ?>

        <div class="admin-users__vip-meta<?= $vipSummary['expired'] ? ' is-expired' : '' ?>">

          <a class="link-gold" href="/admin/vip-kurumsal.php?q=<?= urlencode((string) $r['username']) ?>">VIP yönet →</a>

          · <?= cx_e($vipSummary['status_label']) ?>

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

      <td class="admin-users__actions">

        <?php if ($protected): ?>

          <em>Superadmin — degistirilemez</em>

        <?php elseif ($isVip): ?>

          <a class="btn-sm" href="/admin/vip-kurumsal.php?q=<?= urlencode((string) $r['username']) ?>">VIP paneli</a>
          <form method="post" class="admin-user-delete-form" onsubmit="return confirm('<?= cx_e('VIP Kurumsal hesap kalıcı silinsin mi? ' . $total . ' ilan da kaldırılır.') ?>')">
            <?= cx_csrf_field() ?>
            <input type="hidden" name="action" value="delete_user">
            <input type="hidden" name="user_id" value="<?= $rid ?>">
            <button class="admin-btn admin-btn--danger btn-sm" type="submit">Üye sil</button>
          </form>

        <?php else: ?>

        <form method="post" class="role-form">

          <?= cx_csrf_field() ?>

          <input type="hidden" name="action" value="assign_role">

          <input type="hidden" name="user_id" value="<?= $rid ?>">

          <input type="hidden" name="username_hint" value="<?= cx_e((string) $r['username']) ?>">

          <select name="role" class="role-form__role">

            <?php foreach ($userAssignable as $roleKey): ?>

            <option value="<?= cx_e($roleKey) ?>"<?= $current === $roleKey ? ' selected' : '' ?>>

              <?= cx_e($labels[$roleKey] ?? $roleKey) ?>

            </option>

            <?php endforeach; ?>

          </select>

          <button class="btn" type="submit">Kaydet</button>

        </form>

        <form method="post" class="admin-user-delete-form" onsubmit="return confirm('<?= cx_e((string) $r['username']) ?> kalıcı silinsin mi?<?= $total > 0 ? ' ' . $total . ' ilan da kaldırılır.' : '' ?>')">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="action" value="delete_user">
          <input type="hidden" name="user_id" value="<?= $rid ?>">
          <button class="admin-btn admin-btn--danger btn-sm" type="submit">Üye sil</button>
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

  <strong>Roller:</strong> Onaycı · Yönetici · Üye · Kurumsal (Galeri) · VIP Kurumsal →

  <a class="link-gold" href="/admin/vip-kurumsal.php">ayrı yönetim sayfası</a>

</p>

<?php

$content = ob_get_clean();

$title = 'Kullanıcılar';

$layout = 'admin';

$bodyClass = 'page-admin';

require dirname(__DIR__) . '/views/layout.php';

