<?php
declare(strict_types=1);
/** @var string $adminTab */
$adminTab = $adminTab ?? 'listings';
?>
<nav class="admin-tabs">
  <a class="admin-tabs__item<?= $adminTab === 'listings' ? ' active' : '' ?>" href="/admin/">Ilanlar</a>
  <?php if (cx_is_superadmin($user ?? null)): ?>
  <a class="admin-tabs__item<?= $adminTab === 'users' ? ' active' : '' ?>" href="/admin/users.php">Kullanicilar / Roller</a>
  <a class="admin-tabs__item<?= $adminTab === 'seo' ? ' active' : '' ?>" href="/admin/seo-settings.php">SEO & Webmaster</a>
  <?php endif; ?>
</nav>
