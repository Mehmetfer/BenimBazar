<?php
declare(strict_types=1);
/** @var string $q */
/** @var string $cat */
/** @var string $subcat */
/** @var string $veh */
/** @var string $region */
/** @var string $kktcCity */
/** @var array<string,mixed>|null $user */

$q = $q ?? '';
$cat = $cat ?? 'TÜM TAKASLAR';
$subcat = $subcat ?? '';
$veh = $veh ?? '';
$region = $region ?? cx_region_from_request($user ?? null);
$kktcCity = $kktcCity ?? cx_kktc_city_from_request();
$user = $user ?? null;

$monthsTr = [
    1 => 'Ocak', 2 => 'Şubat', 3 => 'Mart', 4 => 'Nisan', 5 => 'Mayıs', 6 => 'Haziran',
    7 => 'Temmuz', 8 => 'Ağustos', 9 => 'Eylül', 10 => 'Ekim', 11 => 'Kasım', 12 => 'Aralık',
];
$today = (int) date('j') . ' ' . ($monthsTr[(int) date('n')] ?? '') . ', ' . date('Y');
$homeMarketIconsOnly = !empty($homeMarketIconsOnly);
?>
<section class="home-market" aria-label="Pazar yeri">
  <?php if (!$homeMarketIconsOnly): ?>
  <div class="home-market__top">
    <?php if ($veh === ''): ?>
    <a class="home-market__all-cats" href="/index.php?veh=tum-araclar">TÜM ARAÇLAR</a>
    <?php else: ?>
    <span class="home-market__top-spacer" aria-hidden="true"></span>
    <?php endif; ?>
    <span class="home-market__date"><?= cx_e($today) ?></span>
  </div>

  <form class="home-market__search" method="get">
    <?php foreach (cx_region_query_params($user) as $rk => $rv): ?>
      <input type="hidden" name="<?= cx_e($rk) ?>" value="<?= cx_e($rv) ?>">
    <?php endforeach; ?>
    <?php if (!empty($veh)): ?>
      <input type="hidden" name="veh" value="<?= cx_e($veh) ?>">
    <?php elseif ($subcat !== ''): ?>
      <input type="hidden" name="subcat" value="<?= cx_e($subcat) ?>">
    <?php elseif ($cat !== 'TÜM TAKASLAR' && !cx_meta_category($cat)): ?>
      <input type="hidden" name="cat" value="<?= cx_e($cat) ?>">
    <?php endif; ?>
    <input class="home-market__search-input" type="search" name="q" value="<?= cx_e($q) ?>" placeholder="Marka, model, galeri veya ilan no ara…">
    <button class="home-market__search-btn" type="submit" aria-label="Ara">Ara</button>
  </form>
  <?php endif; ?>

  <div id="kategoriler" class="home-market__icon-grid" role="navigation" aria-label="Kategoriler">
    <?php foreach (cx_home_icon_categories() as $iconCat): ?>
      <?php
        $isGalleries = ($iconCat['slug'] ?? '') === 'galeriler';
        $active = $isGalleries
            ? cx_home_galleries_nav_active()
            : cx_home_filter_active($iconCat, $subcat, $veh, $cat);
        $href = (string) ($iconCat['href'] ?? cx_home_category_href($q, $iconCat['slug'], $iconCat['veh'] ?? null));
      ?>
      <a class="home-market__icon-item<?= $active ? ' is-active' : '' ?>" href="<?= cx_e($href) ?>">
        <span class="home-market__icon-circle" aria-hidden="true"><?= $iconCat['icon'] ?></span>
        <span class="home-market__icon-label"><?= cx_e($iconCat['label']) ?></span>
      </a>
    <?php endforeach; ?>
  </div>
</section>
