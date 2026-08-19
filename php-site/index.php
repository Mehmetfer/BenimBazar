<?php



declare(strict_types=1);



require __DIR__ . '/bootstrap.php';

require_once __DIR__ . '/app/Services/SocialService.php';

require_once __DIR__ . '/app/Services/ListingService.php';

require_once __DIR__ . '/app/Services/SellerPublicService.php';



use App\Services\ListingService;

use App\Services\SellerPublicService;



$listings = [];

$galleryHits = [];

$error = null;

$user = null;

$app = [];

$q = '';

$cat = 'TÜM TAKASLAR';

$subcat = '';

$veh = '';

$vehicleBrowse = false;
$showSold = false;
$region = '';
$kktcCity = '';
$feedSort = 'date_desc';
$seoRoute = null;



try {

    cx_bootstrap();

    $seoRoute = null;
    if (cx_seo_landing_enabled() && !empty($_GET['__seo_path'])) {
        $parsed = cx_seo_route_parse((string) $_GET['__seo_path']);
        if ($parsed === null) {
            http_response_code(404);
            $title = 'Sayfa bulunamadı';
            $layout = 'app';
            $navActive = 'home';
            $bodyClass = 'page-not-found';
            ob_start();
            echo '<section class="not-found"><h1>Sayfa bulunamadı</h1><p><a href="/index.php">Ana sayfaya dön</a></p></section>';
            $content = ob_get_clean();
            require __DIR__ . '/views/layout.php';
            exit;
        }
        cx_seo_route_apply($parsed);
        $seoRoute = $parsed;
        unset($_GET['__seo_path']);
    }

    $app = cx_app_config();

    $user = cx_current_user();

    $base = (int) ($app['listing_no_base'] ?? 1000000000);



    if (!empty($_GET['ilan'])) {

        $id = cx_parse_listing_no((string) $_GET['ilan'], $base);

        if ($id !== null) {

            cx_redirect('/listing.php?id=' . $id);

        }

    }



    $q = trim((string) ($_GET['q'] ?? ''));

    $cat = trim((string) ($_GET['cat'] ?? 'TÜM TAKASLAR'));

    $subcat = trim((string) ($_GET['subcat'] ?? ''));

    $veh = trim((string) ($_GET['veh'] ?? ''));

    if (!cx_vehicle_browse_active($veh)) {

        $veh = '';

    }

    if ($subcat !== '' && cx_marketplace_by_slug($subcat) === null) {

        $subcat = '';

    }

    if ($veh === '' && $subcat !== '') {
        $subRow = cx_marketplace_by_slug($subcat);
        if ($subRow !== null) {
            $veh = $subRow['veh'];
        }
    }

    if ($veh === '') {

        if ($subcat === '') {

            if (!in_array($cat, cx_categories(), true)) {

                $cat = 'TÜM TAKASLAR';

            }

        } else {

            $cat = 'TÜM TAKASLAR';

        }

    } else {

        $cat = 'TÜM TAKASLAR';

        $subcat = '';

    }



    $showSold = !empty($_GET['show_sold']);

    $region = cx_region_from_request($user);
    $kktcCity = cx_kktc_city_from_request();
    $feedSort = cx_listing_sort_from_request();

    $svc = new ListingService($base);

    if ($veh !== '') {

        $vehicleFilters = cx_vehicle_filters_from_request($veh);

        $listings = $svc->vehicleBrowseFeed(

            $q !== '' ? $q : null,

            $user ? (int) $user['id'] : null,

            $veh,

            $vehicleFilters,

            $showSold,

            $region,

            $kktcCity,

            $feedSort

        );

    } else {

        $listings = $svc->publicFeed(

            $q !== '' ? $q : null,

            $user ? (int) $user['id'] : null,

            cx_meta_category($cat) ? null : $cat,

            $subcat !== '' ? $subcat : null,

            $showSold,

            $region,

            $kktcCity,

            $feedSort

        );

    }

    $vehicleBrowse = cx_vehicle_browse_active($veh);

    if ($q !== '') {
        try {
            $galleryHits = (new SellerPublicService($base))->searchGalleries($q, 12);
        } catch (Throwable) {
            $galleryHits = [];
        }
    }

} catch (Throwable $e) {

    $error = $e->getMessage();

}



ob_start();

if ($error !== null) {

    echo '<p class="alert alert-error">' . cx_e($error) . '</p>';

} else {

    $compact = true;

    require __DIR__ . '/views/partials/brand.php';

?>

<div class="home-greet-row home-greet-row--market">

  <span class="home-greet"><?= $user ? 'Merhaba, ' . cx_e($user['username']) : 'Hoş geldiniz' ?></span>

  <span class="spacer"></span>

  <?php require __DIR__ . '/views/partials/site-flags.php'; ?>

  <?php if ($user): ?>

    <?php if (cx_is_staff($user)): ?>

      <a class="link-gold" href="/admin/">Yönetim</a>

      <?php if (cx_is_superadmin($user)): ?>

      <a class="link-gold" href="/admin/users.php">Roller</a>

      <?php endif; ?>

    <?php endif; ?>

    <?php if (cx_is_vip_kurumsal($user)): ?>
      <a class="link-gold" href="/gallery-panel.php">Mağaza paneli</a>
    <?php endif; ?>

    <a class="link-gold" href="/favorites.php">Favoriler</a>

    <a class="link-gold" href="/logout.php">Çıkış</a>

  <?php else: ?>

    <a class="link-gold" href="/login.php">Giriş</a>

    <a class="link-gold" href="/register.php">Kayıt ol</a>

  <?php endif; ?>

</div>



<?php require __DIR__ . '/views/partials/home-market.php'; ?>

<?php if (!empty($region) && $region === 'kktc'): ?>
  <?php require __DIR__ . '/views/partials/kktc-city-filter.php'; ?>
<?php endif; ?>



<?php if ($q !== '' && $galleryHits !== []): ?>
  <?php require __DIR__ . '/views/partials/home-galleries.php'; ?>
<?php endif; ?>

<?php if ($seoRoute !== null): ?>
  <?php
    $breadcrumbs = cx_seo_route_breadcrumbs($seoRoute);
    require __DIR__ . '/views/partials/seo-breadcrumbs.php';
  ?>
<?php endif; ?>



<?php
  $vehicleFilters = $vehicleBrowse ? cx_vehicle_filters_from_request($veh) : [];
  $vehicleCount = count($listings);
  $vehicleBrowseStep = $vehicleBrowse ? cx_vehicle_browse_step($veh, $vehicleFilters) : 'listings';
  $feedTitle = 'Yeni öneriler';
  if (!empty($region) && $region === 'kktc') {
      require_once __DIR__ . '/app/Helpers/kktc-locations.php';
      $cityLabel = cx_kktc_city_label($kktcCity);
      $feedTitle = $cityLabel !== ''
          ? 'KKTC · ' . $cityLabel . ' (' . $vehicleCount . ')'
          : 'KKTC · Girne / Mağusa / Sterlin (£) (' . $vehicleCount . ')';
  } elseif ($vehicleBrowse) {
      if ($vehicleBrowseStep === 'type') {
          $feedTitle = 'Ticari Araç — tür seçin';
      } elseif ($vehicleBrowseStep === 'brand') {
          if ($veh === 'ticari') {
              $feedTitle = cx_vehicle_commercial_type_short((string) $vehicleFilters['commercial_type']) . ' — marka seçin';
          } else {
              $feedTitle = cx_vehicle_segment_label($veh) . ' — marka seçin';
          }
      } elseif ($vehicleBrowseStep === 'model') {
          $rawMake = $vehicleFilters['make'] ?? [];
          $makeLabel = is_array($rawMake) && $rawMake !== [] ? (string) $rawMake[0] : 'Marka';
          $feedTitle = $makeLabel . ' — model seçin';
      } else {
          if (cx_vehicle_is_all_mode($veh) && cx_vehicle_filters_active($vehicleFilters)) {
              $feedTitle = 'Tüm Araçlar — filtreli (' . $vehicleCount . ')';
          } else {
              $feedTitle = cx_vehicle_segment_label($veh) . ' (' . $vehicleCount . ')';
          }
      }
  } else {
      $label = cx_home_filter_label($subcat, '', $cat);
      $feedTitle = $label !== '' ? $label . ' (' . $vehicleCount . ')' : 'Yeni öneriler';
  }
  if ($seoRoute !== null && $vehicleBrowseStep === 'listings') {
      $feedTitle = cx_seo_meta_for_route($seoRoute, $vehicleCount)['h1']
          . ($vehicleCount > 0 ? ' (' . $vehicleCount . ')' : '');
  }
  $clearHref = $vehicleBrowse
      ? ($vehicleBrowseStep === 'model'
          ? ($veh === 'ticari'
              ? cx_vehicle_filter_href('ticari', $q, ['commercial_type' => $vehicleFilters['commercial_type'] ?? null])
              : cx_vehicle_filter_href($veh, $q, []))
          : ($vehicleBrowseStep === 'brand'
              ? ($veh === 'ticari'
                  ? cx_vehicle_filter_href('ticari', $q, [])
                  : cx_vehicle_filter_href($veh, $q, []))
              : cx_vehicle_filter_href($veh, $q, [])))
      : '/index.php';
  $createHref = $vehicleBrowse
      ? (cx_vehicle_is_all_mode($veh) ? '/create-listing.php' : '/create-listing.php?veh=' . rawurlencode($veh))
      : ($subcat !== ''
          ? '/create-listing.php?subcat=' . rawurlencode($subcat)
          : '/create-listing.php');
?>

<div class="home-market__feed<?= $vehicleBrowse ? ' home-market__feed--vehicle' : '' ?>">
  <?php if ($vehicleBrowse): ?>
  <button type="button" class="vehicle-filters-toggle" data-vehicle-filters-open>
    ☰ Filtreler<?= cx_vehicle_filters_active($vehicleFilters) ? ' •' : '' ?>
  </button>
  <div class="vehicle-browse">
    <?php require __DIR__ . '/views/partials/vehicle-filters.php'; ?>
    <div class="vehicle-browse__results">
  <?php endif; ?>

  <div class="home-market__feed-head">
    <h2 class="home-market__feed-title"><?= cx_e($feedTitle) ?></h2>
    <div class="home-market__feed-tools">
    <?php if (cx_listing_sort_enabled()): ?>
      <label class="home-market__sort">
        <span class="visually-hidden">Sıralama</span>
        <select class="home-market__sort-select" aria-label="Sıralama" onchange="if(this.value){window.location.href=this.value;}">
          <?php foreach (cx_listing_sort_options() as $sortCode => $sortLabel): ?>
            <option value="<?= cx_e(cx_listing_sort_href($sortCode)) ?>"<?= $feedSort === $sortCode ? ' selected' : '' ?>><?= cx_e($sortLabel) ?></option>
          <?php endforeach; ?>
        </select>
      </label>
    <?php endif; ?>
    <?php
      $soldQs = $_GET;
      if ($showSold) {
          unset($soldQs['show_sold']);
          $soldLabel = 'Satilmislari gizle';
      } else {
          $soldQs['show_sold'] = '1';
          $soldLabel = 'Satilmis ilanlari goster';
      }
      $soldHref = '/index.php?' . http_build_query($soldQs);
    ?>
    <a class="home-market__feed-clear" href="<?= cx_e($soldHref) ?>"><?= cx_e($soldLabel) ?></a>
    <?php if ($vehicleBrowse || $subcat !== '' || $cat !== 'TÜM TAKASLAR' || (!empty($region) && $region === 'kktc')): ?>
      <?php
        $cityClearHref = '';
        if (!empty($region) && $region === 'kktc' && $kktcCity !== '' && !$vehicleBrowse && $subcat === '' && $cat === 'TÜM TAKASLAR') {
            $cityClearParams = cx_region_query_params();
            unset($cityClearParams['city']);
            $cityClearHref = '/index.php?' . http_build_query($cityClearParams, '', '&', PHP_QUERY_RFC3986);
        }
        $feedClearHref = (!empty($region) && $region === 'kktc' && !$vehicleBrowse && $subcat === '' && $cat === 'TÜM TAKASLAR' && $kktcCity === '')
            ? cx_kktc_region_clear_href()
            : ($cityClearHref !== '' ? $cityClearHref : $clearHref);
      ?>
      <a class="home-market__feed-clear" href="<?= cx_e($feedClearHref) ?>"><?php
        if (!empty($region) && $region === 'kktc' && !$vehicleBrowse && $subcat === '' && $cat === 'TÜM TAKASLAR' && $kktcCity === '') {
            echo 'KKTC filtresini kaldır';
        } elseif (!empty($region) && $region === 'kktc' && $kktcCity !== '' && !$vehicleBrowse && $subcat === '' && $cat === 'TÜM TAKASLAR') {
            echo 'Şehir filtresini kaldır';
        } elseif ($vehicleBrowseStep === 'brand') {
            echo $veh === 'ticari' ? 'Türe dön' : 'Tümünü göster';
        } elseif ($vehicleBrowseStep === 'model') {
            echo 'Markaya dön';
        } else {
            echo 'Tümünü göster';
        }
      ?></a>
    <?php endif; ?>
    </div>
  </div>



<?php if ($vehicleBrowseStep === 'type'): ?>
  <?php
    $context = 'main';
    require __DIR__ . '/views/partials/vehicle-commercial-type-picker.php';
  ?>
<?php elseif ($vehicleBrowseStep === 'brand'): ?>
  <?php
    $filters = $vehicleFilters;
    require __DIR__ . '/views/partials/vehicle-brand-picker-main.php';
  ?>
<?php elseif ($vehicleBrowseStep === 'model'): ?>
  <?php
    $filters = $vehicleFilters;
    require __DIR__ . '/views/partials/vehicle-model-picker-main.php';
  ?>
<?php elseif ($listings === []): ?>

  <p class="home-market__empty">

    <?= $vehicleBrowse ? 'Bu filtrelere uygun araç ilanı bulunamadı.' : 'Henüz ilan yok.' ?>

    <?php if (cx_is_staff($user ?? null)): ?>

      <a href="/kurulum.php">Kurulum</a> sayfasından örnek ilanları yükleyin.

    <?php else: ?>

      İlk ilanı sen ver.

    <?php endif; ?>

  </p>

<?php else: ?>

<div class="home-market__grid<?= $vehicleBrowse ? ' home-market__grid--vehicle' : '' ?>">

<?php

  $feedAds = cx_feed_ads_for_grid($user, $createHref);
  $feedAdInsertAt = cx_feed_ad_insert_after() + 1;
  $ctaInserted = false;
  $i = 0;

  foreach ($listings as $item):

    $i++;

    if (!$ctaInserted && $feedAds !== [] && $i === $feedAdInsertAt):

      $ctaInserted = true;

      require __DIR__ . '/views/partials/market-feed-ad-slot.php';

    endif;

    $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]', $app['uploads_url'] ?? '/uploads');

    $thumb = $photos[0] ?? '';

    $siteUrl = (string) ($app['url'] ?? '');

    $uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');

    $vehicleLine = $vehicleBrowse ? cx_listing_vehicle_summary_line($item) : '';

    $featured = (int) ($item['favorite_count'] ?? 0) >= 2;
    $isSold = !empty($item['is_sold']);
    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));

    $favFormCard = $user
      ? cx_favorite_toggle_form(
          (int) $item['id'],
          '/index.php',
          !empty($item['is_favorited']),
          'market-card__fav-link'
      )
      : '';

?>
  <article class="market-card<?= $vehicleBrowse ? ' market-card--vehicle' : '' ?><?= $isSold ? ' market-card--sold' : '' ?>">

    <a class="market-card__media" href="/listing.php?id=<?= (int) $item['id'] ?>">

      <?php if ($thumb): ?>

        <?= cx_photo_img($thumb, 'card', ['class' => 'market-card__img', 'alt' => ''], $siteUrl, $uploadsUrl) ?>

      <?php else: ?>

        <div class="market-card__img market-card__img--empty">Fotoğraf yok</div>

      <?php endif; ?>

      <?php if ($isSold): ?>
        <span class="market-card__sold-ribbon">SATILDI</span>
      <?php elseif ($mode === 'SALE'): ?>
        <span class="market-card__badge market-card__badge--sale">SATILIK</span>
      <?php else: ?>
        <span class="market-card__badge market-card__badge--trade">TAKAS</span>
      <?php endif; ?>

      <?php if ($featured && !$isSold): ?>
        <span class="market-card__badge market-card__badge--featured">ÖNE ÇIKAN</span>
      <?php endif; ?>

      <span class="market-card__fav<?= !empty($item['is_favorited']) ? ' is-on' : '' ?>" aria-hidden="true">♥</span>

    </a>

    <?php if ($user): ?>
    <?= $favFormCard ?>
    <?php else: ?>
    <a class="market-card__fav-link" href="<?= cx_e(cx_login_url('/listing.php?id=' . (int) $item['id'], 'Favori icin giris yapin')) ?>" aria-label="Favorilere ekle">♥</a>
    <?php endif; ?>

    <div class="market-card__body">

      <div class="market-card__price"><?= cx_e(cx_listing_price_line($item)) ?></div>

      <div class="market-card__meta">

        <span><?= cx_e(cx_listing_card_stats_line($item)) ?></span>

        <span><?= cx_e(cx_listing_location_line($item)) ?></span>

      </div>

      <h3 class="market-card__title">

        <a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_e($item['title']) ?></a>

      </h3>

      <?php if ($vehicleLine !== ''): ?>

      <p class="market-card__vehicle-line"><?= cx_e($vehicleLine) ?></p>

      <?php endif; ?>

      <div class="market-card__actions">

        <a class="market-card__action" href="/listing.php?id=<?= (int) $item['id'] ?>" title="Detay">👁</a>

        <?php if ($user && cx_messages_enabled()): ?>

        <a class="market-card__action" href="<?= cx_e(cx_message_listing_url((int) $item['id'])) ?>" title="Mesaj">💬</a>

        <?php endif; ?>

      </div>

    </div>

  </article>

<?php endforeach; ?>

<?php if (!$ctaInserted && $feedAds !== []): ?>

  <?php require __DIR__ . '/views/partials/market-feed-ad-slot.php'; ?>

<?php endif; ?>

</div>

<?php endif; ?>

<?php if ($vehicleBrowse): ?>
    </div>
  </div>
<?php endif; ?>

</div>

<?php if ($vehicleBrowse): ?>
<script>
function cxBrandLogoFallback(img) {
  if (!img) return;
  var list = (img.getAttribute('data-fallbacks') || '').split('|').filter(Boolean);
  var idx = parseInt(img.getAttribute('data-fallback-idx') || '0', 10);
  if (idx >= list.length) {
    img.style.display = 'none';
    var fb = img.nextElementSibling;
    if (fb && fb.classList.contains('vehicle-brand-picker__logo-fallback')) {
      fb.style.display = 'flex';
    }
    return;
  }
  img.setAttribute('data-fallback-idx', String(idx + 1));
  img.src = list[idx];
}
(function () {
  var panel = document.querySelector('.vehicle-filters');
  var openBtn = document.querySelector('[data-vehicle-filters-open]');
  var closeBtn = document.querySelector('[data-vehicle-filters-close]');
  if (panel && openBtn) {
    openBtn.addEventListener('click', function () {
      panel.classList.add('is-open');
      if (closeBtn) closeBtn.style.display = 'inline-flex';
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        panel.classList.remove('is-open');
      });
    }
  }

  var picker = document.querySelector('[data-brand-picker]');
  if (picker) {
  var brandRow = picker.closest('.vehicle-brand-row');
  var trigger = picker.querySelector('[data-brand-trigger]');
  var panelEl = picker.querySelector('[data-brand-panel]');
  var searchInput = picker.querySelector('[data-brand-search]');
  var summaryEl = picker.querySelector('[data-brand-summary]');
  var modelInput = document.querySelector('[data-brand-model]');
  var checkboxes = picker.querySelectorAll('[data-brand-checkbox]');

  function selectedNames() {
    var out = [];
    checkboxes.forEach(function (cb) {
      if (cb.checked && !cb.disabled) out.push(cb.value);
    });
    return out;
  }

  function updateSummary() {
    var sel = selectedNames();
    var text = 'Marka';
    if (sel.length === 1) text = sel[0];
    else if (sel.length > 1) text = sel[0] + ' +' + (sel.length - 1);
    if (summaryEl) summaryEl.textContent = text;
    if (trigger) trigger.classList.toggle('is-filled', sel.length > 0);
    if (modelInput) {
      modelInput.disabled = sel.length === 0;
      modelInput.classList.toggle('is-disabled', sel.length === 0);
      if (sel.length === 0) modelInput.value = '';
    }
    picker.querySelectorAll('[data-brand-logo-toggle]').forEach(function (btn) {
      var name = btn.getAttribute('data-brand-name');
      btn.classList.toggle('is-selected', sel.indexOf(name) !== -1);
    });
  }

  function closePanel() {
    if (!panelEl || !trigger) return;
    panelEl.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    picker.classList.remove('is-open');
    if (brandRow) brandRow.classList.remove('is-brand-open');
  }

  function openPanel() {
    if (!panelEl || !trigger) return;
    panelEl.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    picker.classList.add('is-open');
    if (brandRow) brandRow.classList.add('is-brand-open');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }

  if (trigger && panelEl) {
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      if (panelEl.hidden) openPanel();
      else closePanel();
    });
  }

  document.addEventListener('click', function (e) {
    if (!picker.contains(e.target)) closePanel();
  });

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      var q = searchInput.value.trim().toLowerCase();
      picker.querySelectorAll('[data-brand-item]').forEach(function (item) {
        var name = item.getAttribute('data-brand-name') || '';
        item.hidden = q !== '' && name.indexOf(q) === -1;
      });
    });
  }

  checkboxes.forEach(function (cb) {
    cb.addEventListener('change', updateSummary);
  });

  picker.querySelectorAll('[data-brand-logo-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-brand-name');
      checkboxes.forEach(function (cb) {
        if (cb.value === name && !cb.disabled) {
          cb.checked = !cb.checked;
        }
      });
      updateSummary();
    });
  });

  updateSummary();
  }

  var brandMain = document.querySelector('[data-brand-main]');
  if (brandMain) {
    var mainSearch = brandMain.querySelector('[data-brand-main-search]');
    if (mainSearch) {
      mainSearch.addEventListener('input', function () {
        var q = mainSearch.value.trim().toLowerCase();
        brandMain.querySelectorAll('[data-brand-main-item]').forEach(function (item) {
          var name = item.getAttribute('data-brand-name') || '';
          item.hidden = q !== '' && name.indexOf(q) === -1;
        });
      });
    }
  }

  var modelMain = document.querySelector('[data-model-main]');
  if (modelMain) {
    var modelSearch = modelMain.querySelector('[data-model-main-search]');
    if (modelSearch) {
      modelSearch.addEventListener('input', function () {
        var q = modelSearch.value.trim().toLowerCase();
        modelMain.querySelectorAll('[data-model-main-item]').forEach(function (item) {
          var name = item.getAttribute('data-model-name') || '';
          item.hidden = q !== '' && name.indexOf(q) === -1;
        });
      });
    }
  }
})();
</script>
<?php endif; ?>

<?php

}

$content = ob_get_clean();
if (!empty(cx_feed_ads_settings()['enabled'])) {
    $content .= '<script src="/assets/feed-ad-slot.js?v=1" defer></script>';
}

if ($seoRoute !== null) {
    $seoMeta = cx_seo_meta_for_route($seoRoute, isset($listings) ? count($listings) : 0);
    $title = $seoMeta['title'];
    $metaDescription = $seoMeta['description'];
    $canonicalUrl = $seoMeta['canonical'];
    $jsonLd = $seoMeta['json_ld'];
    $metaRobots = cx_seo_robots_index();
} else {
    $homeSeo = cx_seo_home_meta();
    $title = $homeSeo['title'];
    $titleStandalone = true;
    $metaDescription = $homeSeo['description'];
    $canonicalUrl = $homeSeo['canonical'];
    $jsonLd = $homeSeo['json_ld'];
}

$layout = 'app';

$navActive = 'home';

$bodyClass = 'page-home-market' . (!empty($vehicleBrowse) ? ' page-vehicle-browse' : '');

require __DIR__ . '/views/layout.php';


