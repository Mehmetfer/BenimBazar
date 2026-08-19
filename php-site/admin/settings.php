<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';

cx_bootstrap();
$user = cx_require_user();

if (!cx_is_superadmin($user)) {
    cx_flash('error', 'Site ayarları yalnızca superadmin içindir.');
    cx_redirect('/admin/');
}

$items = [
    [
        'icon' => '🔍',
        'title' => 'SEO Ayarları',
        'desc' => 'Google, Yandex, Bing doğrulama, Organization Schema ve sosyal medya bağlantıları.',
        'href' => '/admin/seo-settings.php',
        'primary' => true,
    ],
    [
        'icon' => '🖼',
        'title' => 'Filigran',
        'desc' => 'İlan fotoğraflarına toplu filigran uygulama ve yedek yönetimi.',
        'href' => '/admin/watermark-batch.php',
        'primary' => false,
    ],
];

ob_start();
$adminTab = 'settings';
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<div class="admin-settings">
  <header class="admin-settings__head">
    <div>
      <h1 class="admin-settings__title">Ayarlar</h1>
      <p class="admin-settings__lead">Site geneli yapılandırma ve superadmin araçları.</p>
    </div>
  </header>

  <div class="admin-settings__grid">
    <?php foreach ($items as $item): ?>
    <a class="admin-settings__card<?= !empty($item['primary']) ? ' admin-settings__card--primary' : '' ?>" href="<?= cx_e((string) $item['href']) ?>">
      <span class="admin-settings__icon" aria-hidden="true"><?= $item['icon'] ?></span>
      <div class="admin-settings__body">
        <h2 class="admin-settings__card-title"><?= cx_e((string) $item['title']) ?></h2>
        <p class="admin-settings__card-desc"><?= cx_e((string) $item['desc']) ?></p>
      </div>
      <span class="admin-settings__arrow" aria-hidden="true">→</span>
    </a>
    <?php endforeach; ?>
  </div>
</div>

<?php
$content = ob_get_clean();
$title = 'Ayarlar';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
