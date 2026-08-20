<?php

declare(strict_types=1);

/** @var list<array<string,mixed>> $similarListings */
/** @var string $similarMode create|admin */
/** @var string $uploadsUrl */
/** @var string $siteUrl */

$similarListings = $similarListings ?? [];
$similarMode = $similarMode ?? 'admin';
$uploadsUrl = $uploadsUrl ?? (cx_app_config()['uploads_url'] ?? '/uploads');
$siteUrl = $siteUrl ?? (string) (cx_app_config()['site_url'] ?? '');

if ($similarListings === []) {
    return;
}
?>
<div class="similar-listings" data-similar-mode="<?= cx_e($similarMode) ?>">
  <p class="similar-listings__lead">
    <?php if ($similarMode === 'create'): ?>
      Yakın özelliklerde (aynı marka/model/yıl, benzer km) yayında veya onay bekleyen ilanlar var.
      Devam etmek için onay kutucuğunu işaretleyin; ilan yine moderasyona düşer.
    <?php else: ?>
      Bu ilana yakın özelliklerde başka ilanlar bulundu. İnceleyip yine de onaylayabilirsiniz.
    <?php endif; ?>
  </p>
  <ul class="similar-listings__list">
    <?php foreach ($similarListings as $sim): ?>
      <?php
        $simId = (int) ($sim['id'] ?? 0);
        $simNo = (int) ($sim['listing_no'] ?? cx_listing_no($simId));
        $simTitle = (string) ($sim['title'] ?? '');
        $simOwner = (string) ($sim['owner_username'] ?? '—');
        $simStatus = (string) ($sim['status'] ?? '');
        $simThumb = (string) ($sim['thumb'] ?? '');
        $simSpecs = trim(implode(' · ', array_filter([
            (string) ($sim['make'] ?? ''),
            (string) ($sim['model'] ?? ''),
            isset($sim['year']) ? (string) $sim['year'] : '',
            isset($sim['km']) ? number_format((int) $sim['km'], 0, ',', '.') . ' km' : '',
        ])));
        $href = $similarMode === 'admin'
            ? (string) ($sim['admin_url'] ?? '/admin/listing-edit.php?id=' . $simId)
            : (string) ($sim['public_url'] ?? '/listing.php?id=' . $simId);
      ?>
      <li class="similar-listings__item">
        <a class="similar-listings__thumb" href="<?= cx_e($href) ?>"<?= $similarMode === 'admin' ? '' : ' target="_blank" rel="noopener"' ?>>
          <?php if ($simThumb !== ''): ?>
            <?= cx_photo_img($simThumb, 'thumb', ['class' => '', 'alt' => '', 'watermark' => false], $siteUrl, $uploadsUrl) ?>
          <?php else: ?>
            <span class="similar-listings__no-photo">Foto yok</span>
          <?php endif; ?>
        </a>
        <div class="similar-listings__body">
          <div class="similar-listings__top">
            <span class="similar-listings__no">#<?= $simNo ?></span>
            <span class="admin-badge admin-badge--<?= cx_e(cx_listing_status_class($simStatus)) ?>">
              <?= cx_e(cx_listing_status_label($simStatus)) ?>
            </span>
          </div>
          <a class="similar-listings__title" href="<?= cx_e($href) ?>"<?= $similarMode === 'admin' ? '' : ' target="_blank" rel="noopener"' ?>>
            <?= cx_e($simTitle) ?>
          </a>
          <p class="similar-listings__meta">
            @<?= cx_e($simOwner) ?>
            <?php if ($simSpecs !== ''): ?> · <?= cx_e($simSpecs) ?><?php endif; ?>
            <?php if (!empty($sim['location'])): ?> · <?= cx_e((string) $sim['location']) ?><?php endif; ?>
          </p>
        </div>
      </li>
    <?php endforeach; ?>
  </ul>
</div>
