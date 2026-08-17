<?php
declare(strict_types=1);
/** @var bool $compact */
/** @var bool $vertical */
$compact = $compact ?? false;
$vertical = $vertical ?? false;
$name = cx_site_name();
$logoKey = $vertical ? 'logo_vertical' : 'logo_horizontal';
$logoPath = cx_brand_asset_path($logoKey);
if ($logoPath === '') {
    $logoPath = cx_brand_asset_path('logo_horizontal');
}
if ($logoPath === '') {
    $logoPath = '/assets/branding/logo-horizontal.png';
}
$logoClass = 'brand-mark__logo'
    . ($compact ? ' brand-mark__logo--compact' : '')
    . ($vertical ? ' brand-mark__logo--vertical' : '');
?>
<a href="/index.php" class="brand-mark<?= $compact ? ' brand-mark--compact' : '' ?><?= $vertical ? ' brand-mark--vertical' : '' ?> brand-mark__link" aria-label="<?= cx_e($name) ?> — Ana sayfa">
  <img
    class="<?= cx_e($logoClass) ?>"
    src="<?= cx_e($logoPath) ?>?v=20260816logo3"
    alt=""
    width="<?= $vertical ? '220' : ($compact ? '160' : '240') ?>"
    height="<?= $vertical ? '72' : ($compact ? '40' : '56') ?>"
    decoding="async"
  >
  <span class="brand-mark__text">
    <span class="brand-mark__title<?= $compact ? ' brand-mark__title--compact' : '' ?>">
      <span class="brand-mark__benim">Benim</span><span class="brand-mark__bazar">Bazar</span>
    </span>
    <?php if (!$compact): ?>
    <span class="brand-mark__sub"><?= cx_e(cx_site_tagline()) ?></span>
    <?php endif; ?>
  </span>
</a>
