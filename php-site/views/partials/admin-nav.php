<?php
declare(strict_types=1);
/** @var string $adminTab */
$adminTab = $adminTab ?? 'listings';
?>
<nav class="admin-tabs">
  <a class="admin-tabs__item<?= $adminTab === 'listings' ? ' active' : '' ?>" href="/admin/">Ilanlar</a>
  <?php if (cx_is_superadmin($user ?? null)): ?>
  <a class="admin-tabs__item<?= $adminTab === 'users' ? ' active' : '' ?>" href="/admin/users.php">Kullanicilar / Roller</a>
  <?php endif; ?>
</nav>
