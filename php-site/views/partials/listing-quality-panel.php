<?php

declare(strict_types=1);

/** @var string $qualityPanelMode create|edit */
/** @var int $qualityMinPhotos */

$qualityPanelMode = $qualityPanelMode ?? 'create';
$qualityMinPhotos = $qualityMinPhotos ?? 3;
$cfg = cx_listing_quality_settings();

?>
<div class="listing-quality" data-listing-quality data-mode="<?= cx_e($qualityPanelMode) ?>">
  <div class="listing-quality__head">
    <span class="listing-quality__label">Ilan kalitesi</span>
    <strong class="listing-quality__score" data-quality-score>—</strong>
  </div>
  <div class="listing-quality__bar" aria-hidden="true">
    <span class="listing-quality__fill" data-quality-fill style="width:0%"></span>
  </div>
  <ul class="listing-quality__checks" data-quality-checks></ul>
  <p class="listing-quality__hint">En az <?= (int) $qualityMinPhotos ?> fotograf, <?= (int) $cfg['min_description_chars'] ?>+ karakter aciklama<?= $cfg['require_price_on_sale'] ? ' ve satilik ilanlarda fiyat' : '' ?> gerekir.</p>
</div>
