<?php



declare(strict_types=1);



/** @var list<array<string,mixed>> $feedAds */

/** @var array<string,mixed>|null $user */



$feedAds = is_array($feedAds ?? null) ? $feedAds : [];

if ($feedAds === []) {

    return;

}



$intervalMs = cx_feed_ad_rotate_interval_ms();

$multi = count($feedAds) > 1;

$hasBanner = false;

foreach ($feedAds as $ad) {

    if (trim((string) ($ad['image_url'] ?? '')) !== '') {

        $hasBanner = true;

        break;

    }

}

?>

<article

  class="market-card market-feed-ad<?= $hasBanner ? ' market-feed-ad--media' : '' ?><?= !$hasBanner ? ' market-feed-ad--flash' : '' ?>"

  data-feed-ad-slot

  <?= $multi ? ' data-feed-ad-rotate="' . (int) $intervalMs . '"' : '' ?>

  aria-label="Reklam alanı"

>

  <div class="market-feed-ad__inner">

    <?php foreach ($feedAds as $i => $ad): ?>

      <?php

        $theme = preg_replace('/[^a-z0-9_-]/', '', strtolower((string) ($ad['theme'] ?? 'blue'))) ?: 'blue';

        $imageUrl = trim((string) ($ad['image_url'] ?? ''));

        $imageFocus = trim((string) ($ad['image_focus'] ?? '68% 42%'));

        if (!preg_match('/^\d{1,3}%\s+\d{1,3}%$/', $imageFocus)) {

            $imageFocus = '68% 42%';

        }

        $isExternal = !empty($ad['external']);

        $isBanner = $imageUrl !== '';

      ?>

      <div class="market-feed-ad__slide market-feed-ad__slide--<?= cx_e($theme) ?><?= $isBanner ? ' market-feed-ad__slide--banner' : '' ?><?= $i === 0 ? ' is-active' : '' ?>" data-feed-ad-slide>

        <?php if ($isBanner): ?>

          <a

            class="market-feed-ad__banner-link"

            href="<?= cx_e((string) $ad['href']) ?>"

            <?= $isExternal ? ' target="_blank" rel="noopener sponsored"' : '' ?>

            aria-label="<?= cx_e((string) $ad['label']) ?>"

          >

            <img

              class="market-feed-ad__banner"

              src="<?= cx_e($imageUrl) ?>"

              alt="<?= cx_e((string) $ad['label']) ?>"

              style="object-position: <?= cx_e($imageFocus) ?>"

              loading="lazy"

              decoding="async"

            >

          </a>

        <?php else: ?>

          <p class="market-feed-ad__text"><?= cx_e((string) $ad['text']) ?></p>

          <a

            class="market-feed-ad__btn"

            href="<?= cx_e((string) $ad['href']) ?>"

            <?= $isExternal ? ' target="_blank" rel="noopener sponsored"' : '' ?>

          ><?= cx_e((string) $ad['button']) ?></a>

        <?php endif; ?>

        <?php if (($ad['kind'] ?? '') === 'sponsored'): ?>

          <span class="market-feed-ad__tag">Sponsorlu</span>

        <?php endif; ?>

      </div>

    <?php endforeach; ?>

  </div>

  <?php if ($multi): ?>

    <div class="market-feed-ad__dots" aria-hidden="true">

      <?php foreach ($feedAds as $i => $ad): ?>

        <span class="market-feed-ad__dot<?= $i === 0 ? ' is-active' : '' ?>"></span>

      <?php endforeach; ?>

    </div>

  <?php endif; ?>

</article>


