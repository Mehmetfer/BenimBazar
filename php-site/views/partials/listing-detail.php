<?php

declare(strict_types=1);

/** @var array<string,mixed> $item */

/** @var list<string> $photos */

/** @var int $no */

/** @var int $id */

/** @var string $share */

/** @var string $whatsappShare */

/** @var array{text:string,image:string,fallback:string} $waSharePayload */

/** @var array<string,mixed>|null $user */

/** @var int $ownerId */



$mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));

$isSale = $mode === 'SALE';

$isFav = !empty($item['is_favorited']);

$score = (int) round((float) ($item['change_score'] ?? 0));

$quickSpecs = cx_listing_quick_specs($item);

$equipment = cx_listing_equipment($item);

$sellerMeta = cx_listing_seller_meta($item);

$expertiseInfo = cx_listing_expertise($item);
$expertiseHas = !empty($expertiseInfo['has_report']);
$expertisePhotos = [];
$expertiseParts = is_array($expertiseInfo['parts'] ?? null) ? $expertiseInfo['parts'] : [];
$appCfg = $app ?? cx_app_config();
if ($expertiseHas && !empty($expertiseInfo['photos'])) {
    $expertisePhotos = cx_photo_urls($expertiseInfo['photos'], $appCfg['uploads_url'] ?? '/uploads');
}
$expertiseMarked = $expertiseParts !== [] || $expertisePhotos !== [];
$isOtomobil = function_exists('cx_listing_matches_vehicle_segment')
    && cx_listing_matches_vehicle_segment($item, 'otomobil');
$showExpertise = $isOtomobil;

$isVehicle = cx_is_vehicle_listing($item) && $quickSpecs !== [];

$characteristics = cx_listing_characteristics($item, $no, $isSale);

$descRaw = trim((string) ($item['description'] ?? ''));

$descLong = mb_strlen($descRaw) > 320;



$specs = [

    ['icon' => '📅', 'label' => 'Tarih', 'value' => cx_listing_date_short($item) ?: '—'],

    ['icon' => '📍', 'label' => 'Konum', 'value' => cx_listing_location_line($item)],

    ['icon' => '🏷️', 'label' => 'Kategori', 'value' => (string) ($item['category'] ?? '—')],

    ['icon' => '✨', 'label' => 'Durum', 'value' => cx_condition_label((string) ($item['condition'] ?? 'good'))],

    ['icon' => '⇄', 'label' => 'İlan türü', 'value' => $isSale ? 'Satılık' : 'Takas'],

    ['icon' => '🆔', 'label' => 'İlan no', 'value' => (string) $no],

    ['icon' => '⭐', 'label' => 'Change Score', 'value' => $score > 0 ? (string) $score : '—'],

    ['icon' => '📷', 'label' => 'Fotoğraf', 'value' => (string) count($photos)],

];

if ($isSale && !empty($item['price_negotiable'])) {

    $specs[] = ['icon' => '💬', 'label' => 'Pazarlık', 'value' => 'Yapılır'];

}

if (!$isSale) {

    $wanted = trim((string) ($item['wanted_items'] ?? ''));

    $specs[] = ['icon' => '🎯', 'label' => 'Takas isteği', 'value' => $wanted !== '' ? $wanted : 'Açık teklif'];

}

$accept = trim((string) ($item['accept_categories'] ?? ''));

if ($accept !== '') {

    $specs[] = ['icon' => '✅', 'label' => 'Kabul edilen', 'value' => $accept];

}

$features = cx_listing_feature_tags($item);

$listingStatus = strtoupper((string) ($item['status'] ?? ''));
$isPublicListing = cx_listing_is_public($listingStatus);
$isOwner = $user && $ownerId > 0 && (int) $user['id'] === $ownerId;
$canEditOwn = $isOwner && $listingStatus !== 'CANCELLED' && $listingStatus !== 'SOLD';
$canMarkSold = $isOwner && in_array($listingStatus, ['APPROVED', 'ACTIVE'], true);
$canRepublish = $isOwner && ($item['is_expired'] ?? false);
$viewCount = (int) ($item['view_count'] ?? 0);
$messageCount = (int) ($item['message_count'] ?? 0);
$favoriteCount = (int) ($item['favorite_count'] ?? 0);
$isSoldListing = cx_listing_is_sold($listingStatus);
$showMessages = cx_messages_enabled() && $user && !$isOwner && $isPublicListing;
$showFavorite = $user && $isPublicListing;
$showShare = $isPublicListing;

$priceHistorySummary = is_array($priceHistorySummary ?? null) ? $priceHistorySummary : ['points' => []];

$favForm = $showFavorite
    ? cx_favorite_toggle_form($id, '/listing.php?id=' . $id, $isFav, 'listing-action--icon' . ($isFav ? ' is-on' : ''))
    : '';

$priceAlertEnabled = false;
if ($showFavorite && $isFav && cx_price_drop_alerts_enabled()) {
    require_once __DIR__ . '/../../app/Services/PriceDropAlertService.php';
    $priceAlertEnabled = (new \App\Services\PriceDropAlertService())->isAlertEnabled((int) $user['id'], $id);
}
$alertForm = cx_price_alert_toggle_form($id, '/listing.php?id=' . $id, $priceAlertEnabled, $isFav);

$messagesHref = cx_message_listing_url($id);

$sellerType = trim((string) ($sellerMeta['type'] ?? ''));

$sellerPhone = trim((string) ($sellerMeta['phone'] ?? ''));

$sellerWeb = trim((string) ($sellerMeta['website'] ?? ''));

$sellerNav = cx_listing_seller_public_nav($item);
$sellerPublicUrl = (string) ($sellerNav['url'] ?? '');
$sellerHoverHint = (string) ($sellerNav['hint'] ?? 'Kullanıcının diğer ilanlarını gör');
$sellerIsCorporate = !empty($sellerNav['is_corporate']);

$equipmentVisible = 12;

$equipmentHidden = max(0, count($equipment) - $equipmentVisible);

$photoSiteUrl = (string) (cx_app_config()['url'] ?? '');

$photoUploadsUrl = (string) (cx_app_config()['uploads_url'] ?? '/uploads');

$listingBreadcrumbs = $listingBreadcrumbs ?? [];

?>

<?php if ($listingBreadcrumbs !== []): ?>
  <?php
    $breadcrumbs = $listingBreadcrumbs;
    require __DIR__ . '/seo-breadcrumbs.php';
  ?>
<?php endif; ?>

<div class="listing-detail<?= $isVehicle ? ' listing-detail--vehicle' : '' ?>">

  <div class="listing-detail__topbar">
    <?php require __DIR__ . '/site-flags.php'; ?>
    <a class="listing-detail__back" href="/index.php">← İlanlara dön</a>
  </div>

  <div class="listing-detail__layout">

    <div class="listing-detail__main">

      <div class="listing-gallery" data-gallery>

        <div class="listing-gallery__stage" data-gallery-stage>

          <?php if ($photos !== []): ?>

            <?php if ($isSoldListing): ?>
              <span class="listing-gallery__sold-ribbon">SATILDI</span>
            <?php endif; ?>

            <?= cx_photo_img($photos[0], 'detail', [
              'class' => 'listing-gallery__hero',
              'loading' => 'eager',
              'data-gallery-hero' => '',
            ], $photoSiteUrl, $photoUploadsUrl) ?>

            <?php if (count($photos) > 1): ?>

              <button type="button" class="listing-gallery__nav listing-gallery__nav--prev" data-gallery-prev aria-label="Önceki fotoğraf">‹</button>

              <button type="button" class="listing-gallery__nav listing-gallery__nav--next" data-gallery-next aria-label="Sonraki fotoğraf">›</button>

            <?php endif; ?>

            <span class="listing-gallery__counter" data-gallery-counter>1 / <?= count($photos) ?></span>

          <?php else: ?>

            <div class="listing-gallery__empty">Fotoğraf yok</div>

          <?php endif; ?>

        </div>

        <?php if (count($photos) > 1): ?>

        <div class="listing-gallery__thumbs">

          <?php foreach ($photos as $i => $url): ?>

            <button type="button" class="listing-gallery__thumb<?= $i === 0 ? ' is-active' : '' ?>" data-gallery-index="<?= $i ?>" data-gallery-src="<?= cx_e(cx_photo_sized($url, 1600, $photoSiteUrl, $photoUploadsUrl)) ?>">

              <?= cx_photo_img($url, 'thumb', ['class' => '', 'alt' => ''], $photoSiteUrl, $photoUploadsUrl) ?>

            </button>

          <?php endforeach; ?>

        </div>

        <?php endif; ?>

      </div>

      <div class="listing-detail__body">

      <?php if ($isVehicle): ?>

      <div class="listing-price-spec" aria-label="Araç özellikleri">

        <?php foreach ($quickSpecs as $spec): ?>

          <div class="listing-price-spec__item">

            <span class="listing-price-spec__icon" aria-hidden="true"><?= $spec['icon'] ?></span>

            <div class="listing-price-spec__body">

              <div class="listing-price-spec__label"><?= cx_e($spec['label']) ?></div>

              <div class="listing-price-spec__value"><?= cx_e($spec['value']) ?></div>

            </div>

          </div>

        <?php endforeach; ?>

      </div>

      <?php else: ?>

      <div class="listing-spec-grid">

        <?php foreach ($specs as $spec): ?>

          <div class="listing-spec-grid__item">

            <span class="listing-spec-grid__icon" aria-hidden="true"><?= $spec['icon'] ?></span>

            <div>

              <div class="listing-spec-grid__label"><?= cx_e($spec['label']) ?></div>

              <div class="listing-spec-grid__value"><?= cx_e($spec['value']) ?></div>

            </div>

          </div>

        <?php endforeach; ?>

      </div>

      <?php endif; ?>



      <?php if ($equipment !== []): ?>

      <section class="listing-equipment" data-equipment>

        <h2 class="listing-equipment__title">Donanım ve özellikler</h2>

        <div class="listing-equipment__grid">

          <?php foreach ($equipment as $i => $label): ?>

            <div class="listing-equipment__item<?= $i >= $equipmentVisible ? ' is-collapsed' : '' ?>">

              <span class="listing-equipment__check" aria-hidden="true">✓</span>

              <span><?= cx_e($label) ?></span>

            </div>

          <?php endforeach; ?>

        </div>

        <?php if ($equipmentHidden > 0): ?>

          <button type="button" class="listing-equipment__more" data-equipment-toggle>

            Daha fazla (<?= $equipmentHidden ?>)

          </button>

        <?php endif; ?>

      </section>

      <?php elseif ($features !== []): ?>

      <section class="listing-features">

        <h2 class="listing-features__title">Özellikler</h2>

        <div class="listing-features__grid">

          <?php foreach ($features as $feat): ?>

            <div class="listing-features__item">

              <span class="listing-features__icon" aria-hidden="true"><?= $feat['icon'] ?></span>

              <span><?= cx_e($feat['label']) ?></span>

            </div>

          <?php endforeach; ?>

        </div>

      </section>

      <?php endif; ?>



      <section class="listing-desc-block" id="aciklama">

        <h2 class="listing-desc-block__title">Açıklama</h2>

        <div class="listing-desc-block__text<?= $descLong ? ' is-collapsed' : '' ?>" data-desc-text><?= nl2br(cx_e($descRaw)) ?></div>

        <?php if ($descLong): ?>

          <button type="button" class="listing-desc-block__more" data-desc-toggle>Daha fazla</button>

        <?php endif; ?>

      </section>



      <?php if ($isVehicle): ?>

      <section class="listing-characteristics">

        <h2 class="listing-characteristics__title">Teknik özellikler</h2>

        <dl class="listing-characteristics__list">

          <?php foreach ($characteristics as $row): ?>

            <div>

              <dt><?= cx_e($row['label']) ?></dt>

              <dd><?= cx_e($row['value']) ?></dd>

            </div>

          <?php endforeach; ?>

        </dl>

      </section>

      <?php endif; ?>

      <?php if ($showExpertise): ?>

      <section class="listing-expertise" aria-label="Ekspertiz raporu">

        <h2 class="listing-expertise__title">Ekspertiz / kaporta</h2>

        <?php if ($expertiseMarked): ?>
        <p class="listing-expertise__lead">Satıcı kaporta/boya durumunu işaretledi<?= $expertisePhotos !== [] ? '; rapor fotoğrafları da ekli.' : '.' ?></p>
        <?php else: ?>
        <p class="listing-expertise__lead">Bu otomobil ilanında henüz kaporta / boya işaretlemesi girilmedi. Satıcı ilanı düzenleyerek ekspertiz ekleyebilir.</p>
        <?php endif; ?>

        <p class="listing-expertise__disclaimer">
          Bu ekspertiz / kaporta bilgileri BenimBazar tarafından bağımsız hazırlanmış resmi bir ekspertiz raporu değildir.
          Bilgiler ilan sahibi tarafından sisteme girilmiş olabilir.
          Araç satın almadan önce bağımsız ekspertiz ve gerekli belge kontrollerinin yapılması önerilir.
          <a class="link-gold" href="/ekspertiz-kosullari.php">Ekspertiz koşulları</a>
        </p>

        <?php
          $expertiseReadonly = true;
          require __DIR__ . '/expertise-diagram.php';
        ?>

        <?php if ($expertisePhotos !== []): ?>

        <div class="listing-expertise__grid">

          <?php foreach ($expertisePhotos as $ei => $exUrl): ?>

            <a class="listing-expertise__item" href="<?= cx_e($exUrl) ?>" target="_blank" rel="noopener" title="Ekspertiz sayfa <?= $ei + 1 ?>">

              <?= cx_photo_img((string) $exUrl, 'thumb', ['class' => '', 'alt' => 'Ekspertiz raporu', 'watermark' => false], (string) ($appCfg['url'] ?? ''), (string) ($appCfg['uploads_url'] ?? '/uploads')) ?>

              <span class="listing-expertise__page">Sayfa <?= $ei + 1 ?></span>

            </a>

          <?php endforeach; ?>

        </div>

        <?php endif; ?>

      </section>

      <?php endif; ?>



      <div class="listing-promo">

        <div class="listing-promo__icon" aria-hidden="true">🛡️</div>

        <div>

          <strong><?= cx_e(cx_site_name()) ?> güvenli alışveriş</strong>

          <p>Doğrulanmış üyeler, güven skoru ve moderasyon ile daha güvenli alışveriş.</p>

        </div>

      </div>

      </div>

    </div>



    <aside class="listing-detail__aside">

      <div class="listing-head">

        <h1 class="listing-head__title"><?= cx_e($item['title']) ?></h1>

        <p class="listing-head__sub"><?= cx_e(cx_listing_subtitle($item)) ?></p>

        <div class="listing-head__stats">
          <span><strong><?= number_format($viewCount, 0, ',', '.') ?></strong> Görüntülenme</span>
          <span><strong><?= number_format($favoriteCount, 0, ',', '.') ?></strong> Favori</span>
          <span><strong><?= number_format($messageCount, 0, ',', '.') ?></strong> Mesaj</span>
        </div>

        <?php if ($canRepublish): ?>
          <div class="listing-expiry-alert">
            ⚠️ Bu ilanın süresi doldu.
            <form method="post" action="/listing-action.php" style="display:inline;margin-left:.5rem">
              <?= cx_csrf_field() ?>
              <input type="hidden" name="action" value="republish">
              <input type="hidden" name="listing_id" value="<?= $id ?>">
              <input type="hidden" name="back" value="/listing.php?id=<?= $id ?>">
              <button type="submit" class="listing-action listing-action--primary">Yeniden Yayınla</button>
            </form>
          </div>
        <?php endif; ?>

        <?php if ($sellerType !== ''): ?>

          <span class="listing-badge listing-badge--dealer"><?= cx_e($sellerType) ?></span>

        <?php endif; ?>

        <?php if (in_array(strtolower((string) ($item['condition'] ?? '')), ['new', 'like_new', 'sifir'], true)): ?>

          <span class="listing-badge listing-badge--warranty">Garantili</span>

        <?php endif; ?>

        <?php if ($score >= 80): ?>

          <span class="listing-badge listing-badge--premium">Premium üye</span>

        <?php endif; ?>

        <?php if ($showExpertise && $expertiseMarked): ?>

          <span class="listing-badge listing-badge--expertise">Ekspertizli</span>

        <?php endif; ?>

      </div>



      <div class="listing-price-block">

        <?php if ($isSale): ?>

          <?php if ($canEditOwn): ?>
            <?php
              $priceAdjustBack = '/listing.php?id=' . $id;
              require __DIR__ . '/price-adjust.php';
              unset($priceAdjustBack);
            ?>
          <?php else: ?>
          <div class="listing-price-block__amount"><?= cx_e(cx_listing_price_line($item)) ?></div>
          <?php endif; ?>

          <?php
            $priceDelta = trim((string) ($priceHistorySummary['delta_label'] ?? ''));
            if ($priceDelta !== '' && !empty($priceHistorySummary['dropped'])):
          ?>
            <div class="listing-price-block__drop"><?= cx_e($priceDelta) ?></div>
          <?php elseif ($priceDelta !== '' && !empty($priceHistorySummary['rose'])): ?>
            <div class="listing-price-block__drop listing-price-block__drop--up"><?= cx_e($priceDelta) ?></div>
          <?php endif; ?>

          <?php if (!empty($item['price_negotiable'])): ?>

            <div class="listing-price-block__note">Pazarlık payı vardır</div>

          <?php endif; ?>

        <?php else: ?>

          <div class="listing-price-block__amount listing-price-block__amount--trade">Takas</div>

          <?php if ($w = trim((string) ($item['wanted_items'] ?? ''))): ?>

            <div class="listing-price-block__note">Karşılık: <?= cx_e($w) ?></div>

          <?php endif; ?>

        <?php endif; ?>

        <?php require __DIR__ . '/price-history.php'; ?>

      </div>

      <?php require __DIR__ . '/market-compare.php'; ?>

      <?php if ($isVehicle && $quickSpecs !== []): ?>

      <div class="listing-aside-specs" aria-label="Özet özellikler">

        <?php foreach (array_slice($quickSpecs, 0, 4) as $spec): ?>

          <div class="listing-aside-specs__item">

            <span class="listing-aside-specs__label"><?= cx_e($spec['label']) ?></span>

            <span class="listing-aside-specs__value"><?= cx_e($spec['value']) ?></span>

          </div>

        <?php endforeach; ?>

      </div>

      <?php endif; ?>



      <div class="listing-action-row">

        <?php if ($canEditOwn): ?>
        <a class="listing-action listing-action--primary" href="/edit-listing.php?id=<?= $id ?>">Ilanimi duzenle</a>
        <?php endif; ?>
        <?php if ($canMarkSold): ?>
        <form method="post" action="/listing-action.php" style="display:inline" onsubmit="return confirm('Bu ilan satildi olarak isaretlenecek. Devam etmek istiyor musunuz?')">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="action" value="mark_sold">
          <input type="hidden" name="listing_id" value="<?= $id ?>">
          <input type="hidden" name="back" value="/listing.php?id=<?= $id ?>">
          <button type="submit" class="listing-action">✓ Satildi olarak isaretle</button>
        </form>
        <?php elseif ($canRepublish): ?>
        <form method="post" action="/listing-action.php" style="display:inline">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="action" value="republish">
          <input type="hidden" name="listing_id" value="<?= $id ?>">
          <input type="hidden" name="back" value="/listing.php?id=<?= $id ?>">
          <button type="submit" class="listing-action listing-action--primary">Yeniden Yayinla</button>
        </form>
        <?php elseif ($showMessages): ?>
        <a class="listing-action listing-action--primary" href="<?= cx_e($messagesHref) ?>">
          <?= $isSale ? 'Teklif ver / Mesaj' : 'Takas teklifi' ?>
        </a>
        <?php elseif ($isOwner && !$isPublicListing): ?>
        <span class="listing-action listing-action--muted">Moderasyon bekleniyor</span>
        <?php endif; ?>

        <?php if ($showFavorite): ?>
        <?= $favForm ?>
        <?= $alertForm ?>
        <?php endif; ?>

        <?php if (is_array($marketCompare ?? null)): ?>
        <a class="listing-action listing-action--icon" href="#piyasa" title="Piyasa" aria-label="Bu araç piyasada nasıl?">⚖</a>
        <?php endif; ?>
        <?php if ($showShare): ?>
        <a class="listing-action listing-action--icon" href="/share.php?id=<?= $id ?>" title="Paylaş">↗</a>
        <?php endif; ?>

      </div>



      <div class="listing-seller main-seller-info">

        <?php if ($sellerPublicUrl !== ''): ?>
        <a class="listing-seller__link<?= $sellerIsCorporate ? ' listing-seller__link--gallery' : '' ?>"
           href="<?= cx_e($sellerPublicUrl) ?>"
           aria-label="<?= cx_e($sellerHoverHint) ?>">
          <span class="listing-seller__name"><?= cx_e(cx_listing_seller_display_name($item)) ?></span>
          <span class="listing-seller__hint" aria-hidden="true"><?= cx_e($sellerHoverHint) ?></span>
        </a>
        <?php else: ?>
        <div class="listing-seller__name"><?= cx_e(cx_listing_seller_display_name($item)) ?></div>
        <?php endif; ?>

        <?php $sellerProfileLine = cx_listing_seller_profile_line($item); if ($sellerProfileLine !== ''): ?>
        <div class="listing-seller__profile"><?= cx_e($sellerProfileLine) ?></div>
        <?php endif; ?>

        <div class="listing-seller__loc">📍 <?= cx_e(cx_listing_location_line($item)) ?></div>

        <?php if (cx_listing_owner_phone_verified($item)): ?>
        <div class="listing-seller__verified"><?= cx_phone_verified_badge_html() ?></div>
        <?php endif; ?>

        <?php if ($score > 0): ?>

          <div class="listing-seller__score">Change Score: <strong><?= $score ?></strong></div>

        <?php endif; ?>

        <?php if ($sellerPhone !== '' || $sellerWeb !== ''): ?>

        <div class="listing-seller__misc seller-misc-info">

          <?php if ($sellerPhone !== ''): ?>

            <a class="listing-seller__chip" href="tel:<?= cx_e(preg_replace('/\s+/', '', $sellerPhone) ?? $sellerPhone) ?>">📞 <?= cx_e($sellerPhone) ?></a>

          <?php endif; ?>

          <?php if ($sellerWeb !== ''): ?>

            <a class="listing-seller__chip" target="_blank" rel="noopener" href="<?= cx_e($sellerWeb) ?>">🌐 Web sitesi</a>

          <?php endif; ?>

        </div>

        <?php endif; ?>

        <?php if ($sellerPublicUrl !== ''): ?>
        <div class="listing-seller__more">
          <a class="listing-seller__more-link" href="<?= cx_e($sellerPublicUrl) ?>">
            <?= $sellerIsCorporate ? 'Mağazasına bak →' : 'Diğer ilanlarını gör →' ?>
          </a>
        </div>
        <?php endif; ?>

        <div class="listing-seller__actions">

          <?php if ($showMessages): ?>
          <a class="listing-seller__btn listing-seller__btn--msg" href="<?= cx_e($messagesHref) ?>">💬 <?= $isSale ? 'Mesaj' : 'Takas teklifi' ?></a>
          <?php endif; ?>

          <?php if (!$isOwner && $isPublicListing && $sellerPhone !== ''): ?>
          <a class="listing-seller__btn listing-seller__btn--tel" href="tel:<?= cx_e(cx_phone_digits($sellerPhone)) ?>">📞 Ara</a>
          <a class="listing-seller__btn listing-seller__btn--wa" href="<?= cx_e(cx_whatsapp_seller_chat_url($sellerPhone, $item, $id, $no, $photoSiteUrl)) ?>" target="_blank" rel="noopener">WhatsApp</a>
          <?php endif; ?>

          <?php if ($user && $ownerId > 0 && (int) $user['id'] !== $ownerId && $isPublicListing): ?>

          <form method="post" action="/follow-toggle.php" class="listing-seller__follow">

            <?= cx_csrf_field() ?>

            <input type="hidden" name="user_id" value="<?= $ownerId ?>">

            <input type="hidden" name="back" value="/listing.php?id=<?= $id ?>">

            <button type="submit" class="listing-seller__btn listing-seller__btn--follow">

              <?= !empty($item['is_following_owner']) ? 'Takipten çık' : 'Takip et' ?>

            </button>

          </form>

          <?php elseif (!$user): ?>

          <a class="listing-seller__btn listing-seller__btn--follow" href="<?= cx_e(cx_login_url('/listing.php?id=' . $id)) ?>">Giriş yap</a>

          <?php endif; ?>

        </div>

      </div>



      <div class="listing-tech">

        <h3 class="listing-tech__title">Teknik bilgiler</h3>

        <dl class="listing-tech__list">

          <?php foreach (array_slice($characteristics, 0, 8) as $row): ?>

            <div><dt><?= cx_e($row['label']) ?></dt><dd><?= cx_e($row['value']) ?></dd></div>

          <?php endforeach; ?>

        </dl>

        <a class="listing-tech__more" href="#aciklama">Daha fazla</a>

      </div>



      <div class="listing-share-mini">

        <span class="listing-share-mini__label">Paylaş:</span>

        <a href="/share.php?id=<?= $id ?>">Link</a>

        <a href="#" class="js-wa-share">WhatsApp</a>

      </div>

    </aside>

  </div>

  <?php require __DIR__ . '/listing-mobile-dock.php'; ?>

</div>

<?php if ($similarItems !== []): ?>
  <?php require __DIR__ . '/similar-listings-public.php'; ?>
<?php endif; ?>



<script>

(function () {

  var root = document.querySelector('[data-gallery]');

  if (root) {

    var hero = root.querySelector('[data-gallery-hero]');

    var counter = root.querySelector('[data-gallery-counter]');

    var thumbs = Array.prototype.slice.call(root.querySelectorAll('[data-gallery-index]'));

    if (hero && thumbs.length) {

      var urls = thumbs.map(function (t) { return t.getAttribute('data-gallery-src'); });

      var idx = 0;

      function show(i) {

        idx = (i + urls.length) % urls.length;

        hero.src = urls[idx];

        hero.removeAttribute('srcset');

        hero.removeAttribute('sizes');

        if (counter) counter.textContent = (idx + 1) + ' / ' + urls.length;

        thumbs.forEach(function (t, n) { t.classList.toggle('is-active', n === idx); });

      }

      root.querySelector('[data-gallery-prev]')?.addEventListener('click', function () { show(idx - 1); });

      root.querySelector('[data-gallery-next]')?.addEventListener('click', function () { show(idx + 1); });

      thumbs.forEach(function (t) {

        t.addEventListener('click', function () { show(parseInt(t.getAttribute('data-gallery-index'), 10)); });

      });

      var stage = root.querySelector('[data-gallery-stage]') || hero;
      var touchX = 0;
      var touchY = 0;
      stage.addEventListener('touchstart', function (e) {
        if (!e.changedTouches || !e.changedTouches[0]) return;
        touchX = e.changedTouches[0].clientX;
        touchY = e.changedTouches[0].clientY;
      }, { passive: true });
      stage.addEventListener('touchend', function (e) {
        if (!e.changedTouches || !e.changedTouches[0]) return;
        var dx = e.changedTouches[0].clientX - touchX;
        var dy = e.changedTouches[0].clientY - touchY;
        if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
        show(idx + (dx < 0 ? 1 : -1));
      }, { passive: true });

    }

  }



  var descBtn = document.querySelector('[data-desc-toggle]');

  var descText = document.querySelector('[data-desc-text]');

  if (descBtn && descText) {

    descBtn.addEventListener('click', function () {

      var open = descText.classList.toggle('is-open');

      descText.classList.toggle('is-collapsed', !open);

      descBtn.textContent = open ? 'Daha az' : 'Daha fazla';

    });

  }



  var eqBtn = document.querySelector('[data-equipment-toggle]');

  var eqRoot = document.querySelector('[data-equipment]');

  if (eqBtn && eqRoot) {

    eqBtn.addEventListener('click', function () {

      var open = eqRoot.classList.toggle('is-open');

      eqBtn.textContent = open ? 'Daha az' : eqBtn.getAttribute('data-closed-label') || 'Daha fazla';

    });

    eqBtn.setAttribute('data-closed-label', eqBtn.textContent);

  }

})();

</script>

<?php if ($showExpertise): ?>
<script src="/assets/expertise-diagram.js?v=5"></script>
<?php endif; ?>

<?php if ($showShare && !empty($waSharePayload)): ?>
<script>window.__cxWaShare=<?= json_encode($waSharePayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?>;</script>
<script src="/assets/share-wa.js?v=20260815"></script>
<?php endif; ?>


