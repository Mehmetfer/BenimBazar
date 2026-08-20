<?php

declare(strict_types=1);

/** @var array<string,mixed>|null $marketCompare */

$marketCompare = $marketCompare ?? null;
if (!is_array($marketCompare)) {
    return;
}

$insufficient = !empty($marketCompare['insufficient']) || empty($marketCompare['ok']);
$position = (string) ($marketCompare['position'] ?? 'normal');
?>
<section class="market-compare<?= $insufficient ? ' market-compare--empty' : '' ?>" id="piyasa" aria-label="Bu araç piyasada nasıl?">
  <div class="market-compare__head">
    <h2 class="market-compare__title">Bu araç piyasada nasıl?</h2>
    <?php if (!$insufficient && !empty($marketCompare['context'])): ?>
      <p class="market-compare__context"><?= cx_e((string) $marketCompare['context']) ?></p>
    <?php endif; ?>
  </div>

  <?php if ($insufficient): ?>
    <p class="market-compare__empty"><?= cx_e((string) ($marketCompare['insufficient_label'] ?? 'Bu araç için henüz yeterli piyasa verisi bulunamadı.')) ?></p>
  <?php else: ?>
    <div class="market-compare__verdict market-compare__verdict--<?= cx_e($position) ?>">
      <p class="market-compare__position">
        <span class="market-compare__position-icon" aria-hidden="true"><?= cx_e((string) ($marketCompare['position_icon'] ?? '')) ?></span>
        <?= cx_e((string) ($marketCompare['position_label'] ?? '')) ?>
      </p>
      <?php if (!empty($marketCompare['count_label'])): ?>
        <p class="market-compare__highlight"><?= cx_e((string) $marketCompare['count_label']) ?></p>
      <?php endif; ?>
      <?php if (!empty($marketCompare['avg_diff_label'])): ?>
        <p class="market-compare__highlight"><?= cx_e((string) $marketCompare['avg_diff_label']) ?></p>
      <?php endif; ?>
    </div>

    <dl class="market-compare__stats">
      <div class="market-compare__stat">
        <dt>En düşük</dt>
        <dd><?= cx_e((string) ($marketCompare['min_label'] ?? '')) ?></dd>
      </div>
      <div class="market-compare__stat">
        <dt>Ortalama</dt>
        <dd><?= cx_e((string) ($marketCompare['avg_label'] ?? '')) ?></dd>
      </div>
      <div class="market-compare__stat">
        <dt>En yüksek</dt>
        <dd><?= cx_e((string) ($marketCompare['max_label'] ?? '')) ?></dd>
      </div>
      <div class="market-compare__stat market-compare__stat--wide">
        <dt>Benzer ilanlar</dt>
        <dd><?= (int) ($marketCompare['count'] ?? 0) ?> araç</dd>
      </div>
    </dl>

    <?php if (!empty($marketCompare['browse_url'])): ?>
      <p class="market-compare__actions">
        <a class="market-compare__link" href="<?= cx_e((string) $marketCompare['browse_url']) ?>">Benzer ilanları gör →</a>
      </p>
    <?php endif; ?>

    <p class="market-compare__disclaimer">Yalnızca sitedeki gerçek benzer ilanlara göre hesaplanır; veri uydurulmaz.</p>
  <?php endif; ?>
</section>
