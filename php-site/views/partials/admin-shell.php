<?php
declare(strict_types=1);
/** @var string $adminTab */
/** @var array<string,mixed>|null $user */
$adminTab = $adminTab ?? 'listings';
$user = $user ?? cx_current_user();
$roleLabel = cx_admin_role_label($user);
?>
<header class="admin-shell__header">
  <div class="admin-shell__brand">
    <a href="/admin/" class="admin-shell__logo">
      <?php
        $adminLogo = cx_brand_asset_path('logo_horizontal') ?: '/assets/branding/logo-horizontal.png';
      ?>
      <img class="brand-mark__logo brand-mark__logo--admin" src="<?= cx_e($adminLogo) ?>?v=20260816logo3" width="120" height="28" alt="" decoding="async">
      <span class="brand-mark__title brand-mark__title--compact"><span class="brand-mark__benim">Benim</span><span class="brand-mark__bazar">Bazar</span></span>
      <span class="admin-shell__logo-suffix">Yönetim</span>
    </a>
    <span class="admin-shell__role"><?= cx_e($roleLabel) ?></span>
  </div>
  <div class="admin-shell__links">
    <a href="/index.php">Site</a>
    <a href="/logout.php">Çıkış</a>
  </div>
</header>
<nav class="admin-tabs" aria-label="Yönetim menüsü">
  <a class="admin-tabs__item<?= $adminTab === 'listings' ? ' active' : '' ?>" href="/admin/">İlanlar</a>
  <a class="admin-tabs__item<?= $adminTab === 'pending' ? ' active' : '' ?>" href="/admin/?status=pending">Bekleyen</a>
  <a class="admin-tabs__item<?= $adminTab === 'expired' ? ' active' : '' ?>" href="/admin/?status=expired">Suresi dolan</a>
  <a class="admin-tabs__item<?= $adminTab === 'import' ? ' active' : '' ?>" href="/admin/import.php">Import</a>
  <a class="admin-tabs__item<?= $adminTab === 'topviews' ? ' active' : '' ?>" href="/admin/top-views.php">Goruntulenme</a>
  <?php if (cx_is_admin($user)): ?>
  <a class="admin-tabs__item<?= $adminTab === 'users' ? ' active' : '' ?>" href="/admin/users.php">Kullanıcılar</a>
  <?php endif; ?>
  <?php if (cx_is_superadmin($user)): ?>
  <a class="admin-tabs__item<?= $adminTab === 'watermark' ? ' active' : '' ?>" href="/admin/watermark-batch.php">Filigran</a>
  <?php endif; ?>
</nav>
