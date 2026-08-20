<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SellerPublicService.php';

use App\Services\SellerPublicService;

cx_bootstrap();

if (!cx_gallery_discovery_enabled()) {
    cx_redirect('/index.php');
}

$app = cx_app_config();
$user = cx_current_user();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$cfg = cx_gallery_discovery_settings();

$cityFilter = trim((string) ($_GET['city'] ?? ''));
$roleFilter = trim((string) ($_GET['role'] ?? ''));
$q = trim((string) ($_GET['q'] ?? ''));
$page = max(1, (int) ($_GET['page'] ?? 1));

if (!in_array($roleFilter, ['', 'vip', 'dealer'], true)) {
    $roleFilter = '';
}

$filters = array_filter([
    'city' => $cityFilter,
    'role' => $roleFilter,
    'q' => $q,
    'min_listings' => 1,
], static fn ($v) => $v !== '' && $v !== null);

$svc = new SellerPublicService($base);
$result = $svc->listGalleries($filters, $page, $cfg['per_page']);
$galleries = $result['items'];
$total = $result['total'];
$pages = $result['pages'];

$seo = cx_gallery_directory_seo_meta($total, $cityFilter);

$featuredGalleries = [];
if ($page === 1 && $cityFilter === '' && $roleFilter === '' && $q === '') {
    try {
        $featuredGalleries = $svc->featuredGalleries($cfg['featured_vip'], $cfg['featured_dealer']);
    } catch (Throwable) {
        $featuredGalleries = [];
    }
}

$gallerySearchQ = $q;
$q = '';
$cat = 'TÜM TAKASLAR';
$subcat = '';
$veh = '';
$homeMarketIconsOnly = true;

ob_start();
?>
<?php require __DIR__ . '/views/partials/home-market.php'; ?>
<?php
$q = $gallerySearchQ;
$homeMarketIconsOnly = false;
?>
<section class="gallery-directory">
  <nav class="seo-breadcrumbs" aria-label="Sayfa yolu">
    <a class="seo-breadcrumbs__link" href="/index.php">Ana sayfa</a>
    <span class="seo-breadcrumbs__sep">›</span>
    <span class="seo-breadcrumbs__current">Galeriler</span>
  </nav>

  <?php if ($featuredGalleries !== []): ?>
    <?php
      $hideGalleriesMore = true;
      require __DIR__ . '/views/partials/home-galleries-featured.php';
      $hideGalleriesMore = false;
    ?>
  <?php endif; ?>

  <header class="gallery-directory__head">
    <h1 class="gallery-directory__title"><?= cx_e($seo['title']) ?></h1>
    <p class="gallery-directory__lead"><?= cx_e($seo['description']) ?></p>
    <p class="gallery-directory__count"><?= (int) $total ?> mağaza</p>
  </header>

  <form class="gallery-directory__filters" method="get" action="/galeriler">
    <label class="gallery-directory__field">
      <span>Şehir</span>
      <input type="text" name="city" value="<?= cx_e($cityFilter) ?>" placeholder="Girne, Lefkoşa…">
    </label>
    <label class="gallery-directory__field">
      <span>Tür</span>
      <select name="role">
        <option value="">Tümü</option>
        <option value="vip"<?= $roleFilter === 'vip' ? ' selected' : '' ?>>VIP Kurumsal</option>
        <option value="dealer"<?= $roleFilter === 'dealer' ? ' selected' : '' ?>>Kurumsal</option>
      </select>
    </label>
    <label class="gallery-directory__field gallery-directory__field--grow">
      <span>Ara</span>
      <input type="search" name="q" value="<?= cx_e($q) ?>" placeholder="Galeri adı…">
    </label>
    <button type="submit" class="gallery-directory__submit">Filtrele</button>
  </form>

  <?php require __DIR__ . '/views/partials/gallery-directory-grid.php'; ?>

  <?php if ($pages > 1): ?>
  <nav class="gallery-directory__pager" aria-label="Sayfalar">
    <?php for ($p = 1; $p <= $pages; $p++):
        $qs = array_filter([
            'city' => $cityFilter,
            'role' => $roleFilter,
            'q' => $q,
            'page' => $p > 1 ? $p : null,
        ], static fn ($v) => $v !== '' && $v !== null);
        $href = '/galeriler' . ($qs !== [] ? '?' . http_build_query($qs) : '');
    ?>
      <a class="gallery-directory__page<?= $p === $page ? ' is-active' : '' ?>" href="<?= cx_e($href) ?>"><?= $p ?></a>
    <?php endfor; ?>
  </nav>
  <?php endif; ?>
</section>
<?php
$content = ob_get_clean();

$title = $seo['title'];
$metaDescription = $seo['description'];
$canonicalUrl = $seo['canonical'];
$layout = 'app';
$navActive = 'home';
$bodyClass = 'page-gallery-directory';
require __DIR__ . '/views/layout.php';
