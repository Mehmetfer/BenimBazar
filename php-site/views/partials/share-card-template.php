<?php
/** @var array<string,mixed> $card */
$isStory = ($card['format'] ?? 'square') === 'story';
$cardClass = 'ig-share-card' . ($isStory ? ' ig-share-card--story' : '');
?>
<div id="ig-share-card" class="<?= cx_e($cardClass) ?>" data-width="<?= (int) $card['width'] ?>" data-height="<?= (int) $card['height'] ?>">
  <div class="ig-share-card__photo-wrap">
    <?php if (!empty($card['hero_url'])): ?>
      <img class="ig-share-card__photo" src="<?= cx_e((string) $card['hero_url']) ?>" alt="" crossorigin="anonymous">
    <?php else: ?>
      <div class="ig-share-card__photo-placeholder" aria-hidden="true"></div>
    <?php endif; ?>
  </div>

  <div class="ig-share-card__panel">
    <div class="ig-share-card__brand-col">
      <?php if (!empty($card['logo_url'])): ?>
        <img class="ig-share-card__brand-logo" src="<?= cx_e((string) $card['logo_url']) ?>" alt="">
      <?php else: ?>
        <div class="ig-share-card__brand-mark" aria-hidden="true">
          <svg class="ig-share-card__mark-car" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 78h84l-8-22H26l-8 22Z" stroke="#fff" stroke-width="4" stroke-linejoin="round"/>
            <path d="M26 56h68l10 22" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
            <circle cx="34" cy="78" r="8" stroke="#fff" stroke-width="4"/>
            <circle cx="86" cy="78" r="8" stroke="#fff" stroke-width="4"/>
            <circle cx="72" cy="34" r="22" stroke="#c9a227" stroke-width="5"/>
            <path d="M84 46l14 14" stroke="#c9a227" stroke-width="5" stroke-linecap="round"/>
          </svg>
        </div>
      <?php endif; ?>
      <span class="ig-share-card__brand-slash" aria-hidden="true"></span>
    </div>

    <div class="ig-share-card__info">
      <h2 class="ig-share-card__title"><?= cx_e((string) $card['headline']) ?></h2>

      <div class="ig-share-card__meta-row">
        <?php if (!empty($card['year_label'])): ?>
        <div class="ig-share-card__meta-item">
          <svg class="ig-share-card__icon" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 14h20v10H6z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 14V10h12v4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="11" cy="24" r="2.5" fill="currentColor"/><circle cx="21" cy="24" r="2.5" fill="currentColor"/></svg>
          <span><?= cx_e((string) $card['year_label']) ?></span>
        </div>
        <?php endif; ?>
        <div class="ig-share-card__meta-item ig-share-card__meta-item--price">
          <svg class="ig-share-card__icon" viewBox="0 0 32 32" aria-hidden="true"><path d="M10 10c0-3 2-5 6-5s6 2 6 5-6 11-6 11-6-8-6-11Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 6v3M13 8h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <span><?= cx_e((string) $card['price_display']) ?></span>
        </div>
      </div>

      <div class="ig-share-card__divider" aria-hidden="true"></div>

      <div class="ig-share-card__footer-row">
        <div class="ig-share-card__footer-item">
          <svg class="ig-share-card__icon ig-share-card__icon--sm" viewBox="0 0 32 32" aria-hidden="true"><path d="M10 12h12v12H10z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 12V8h8v4M14 18h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <span><?= cx_e((string) $card['fuel']) ?></span>
        </div>
        <div class="ig-share-card__footer-item">
          <svg class="ig-share-card__icon ig-share-card__icon--sm" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="10" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 14v12M10 26h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M12 20h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <span><?= cx_e((string) $card['transmission']) ?></span>
        </div>
        <div class="ig-share-card__footer-item ig-share-card__footer-item--loc">
          <svg class="ig-share-card__icon ig-share-card__icon--sm" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 6c-4 0-7 3-7 7 0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="16" cy="13" r="2.5" fill="currentColor"/></svg>
          <span><?= cx_e((string) $card['location']) ?></span>
        </div>
        <div class="ig-share-card__footer-item ig-share-card__footer-item--ref">
          <span><?= cx_e((string) $card['listing_ref']) ?></span>
        </div>
      </div>
    </div>
  </div>
</div>
