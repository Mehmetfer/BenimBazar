<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingWriteService.php';

use App\Helpers\Security;
use App\Services\ListingWriteService;

cx_bootstrap();
$user = cx_require_user();
if (cx_phone_verify_required() && !cx_user_phone_verified($user)) {
    cx_flash('error', 'Ilan vermek icin telefon dogrulamasi gerekli.');
    cx_redirect('/verify-phone.php');
}
$app = cx_app_config();
$userIsKktc = cx_user_is_kktc($user);
$quota = cx_user_listing_quota($user);

$prefillSegment = trim((string) ($_GET['veh'] ?? ''));
if (!cx_vehicle_browse_active($prefillSegment)) {
    $prefillSegment = '';
}
$prefillSubcat = trim((string) ($_GET['subcat'] ?? ''));
if ($prefillSubcat !== '' && cx_marketplace_by_slug($prefillSubcat) === null) {
    $prefillSubcat = '';
}
if ($prefillSegment !== '' && $prefillSubcat === '') {
    $vehResolved = cx_resolve_listing_category(null, $prefillSegment);
    $prefillSubcat = $vehResolved['slug'] ?? '';
}

$formError = null;
$prefillForm = [];
$formTitle = '';
$formDescription = cx_listing_default_description();
$formLocation = '';
$formWanted = '';
$formMode = $userIsKktc ? 'SALE' : 'TRADE';
$formPriceTl = '';
$formPriceAmount = '';
$formPriceCurrency = 'GBP';
$formPriceNegotiable = false;
$similarListings = [];
$needsSimilarAck = false;
$expertiseHas = false;
$expertisePartsPrefill = [];

$cxPrefillCreateFromPost = static function () use (
    &$formTitle, &$formDescription, &$formLocation, &$formWanted, &$formMode,
    &$formPriceTl, &$formPriceAmount, &$formPriceCurrency, &$formPriceNegotiable,
    &$prefillSubcat, &$prefillSegment, &$prefillForm, &$expertiseHas, &$expertisePartsPrefill, $userIsKktc
): void {
    $formTitle = trim((string) ($_POST['title'] ?? ''));
    $formDescription = trim((string) ($_POST['description'] ?? ''));
    $formLocation = trim((string) ($_POST['location'] ?? ''));
    $formWanted = trim((string) ($_POST['wanted_items'] ?? ''));
    $formMode = strtoupper(trim((string) ($_POST['listing_mode'] ?? $formMode)));
    if (!in_array($formMode, ['TRADE', 'SALE'], true)) {
        $formMode = $userIsKktc ? 'SALE' : 'TRADE';
    }
    $formPriceTl = trim((string) ($_POST['price_tl'] ?? ''));
    $formPriceAmount = trim((string) ($_POST['price_amount'] ?? ''));
    $formPriceCurrency = strtoupper(trim((string) ($_POST['price_currency'] ?? 'GBP')));
    if (!in_array($formPriceCurrency, ['GBP', 'TRY', 'EUR'], true)) {
        $formPriceCurrency = 'GBP';
    }
    $formPriceNegotiable = !empty($_POST['price_negotiable']);
    $expertiseHas = !empty($_POST['expertise_has']);
    $expertisePartsPrefill = cx_expertise_parts_from_post($_POST);

    $prefillSubcat = trim((string) ($_POST['listing_subcat'] ?? $prefillSubcat));
    $resolvedPrefill = cx_resolve_listing_category($prefillSubcat);
    $prefillSegment = (string) ($resolvedPrefill['veh'] ?? $prefillSegment);

    $prefillForm = [];
    foreach ($_POST as $k => $v) {
        if (is_string($v) && (str_starts_with($k, 'vehicle_') || in_array($k, ['seller_type', 'seller_phone', 'seller_website'], true))) {
            $prefillForm[$k] = $v;
        }
    }
    if ($prefillSegment !== '') {
        $prefillForm['vehicle_segment'] = $prefillSegment;
    }
    $prefillMake = trim((string) ($prefillForm['vehicle_make'] ?? ''));
    $prefillModel = trim((string) ($prefillForm['vehicle_model'] ?? ''));
    if ($prefillModel !== '' && $prefillSegment !== '' && $prefillMake !== ''
        && !cx_vehicle_model_in_catalog($prefillModel, $prefillSegment, $prefillMake)
        && $prefillModel !== cx_vehicle_model_custom_option()) {
        $prefillForm['vehicle_model_custom'] = $prefillModel;
        $prefillForm['vehicle_model'] = cx_vehicle_model_custom_option();
    }
};

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::rateLimit('create_listing', 15, 300);
    Security::requireCsrf();

    if (!$quota['ok']) {
        $formError = $quota['message'];
    } else {
    $mode = strtoupper(trim((string) ($_POST['listing_mode'] ?? 'TRADE')));

    $subcatSlug = trim((string) ($_POST['listing_subcat'] ?? ''));
    $resolved = cx_resolve_listing_category($subcatSlug);
    if ($resolved === null) {
        $formError = 'Geçerli bir kategori seçin (Otomobil, Motosiklet, Bisiklet, Ticari Araç, Antika Araç).';
    } else {
        $post = $_POST;
        $post['vehicle_segment'] = $resolved['veh'];
        if ($userIsKktc && in_array($resolved['veh'], ['otomobil', 'motosiklet', 'ticari', 'antika-arac'], true)) {
            $post['require_steering'] = '1';
        }
        $vehiclePack = cx_vehicle_attrs_from_post($post);

        if ($vehiclePack['error'] !== null) {
            $formError = $vehiclePack['error'];
        } elseif ($vehiclePack['attrs'] === null) {
            $formError = 'Araç teknik bilgilerini doldurun.';
        } else {
            $attrs = $vehiclePack['attrs'];
            $similarListings = cx_listing_find_similar($attrs, 0, 8, (int) $user['id']);
            $ackedSimilar = !empty($_POST['ack_similar']);

            if ($similarListings !== [] && !$ackedSimilar) {
                $needsSimilarAck = true;
                $cxPrefillCreateFromPost();
            } else {
            // Fotoğrafları doğrulama + benzer onayından sonra kaydet
            $newSaved = cx_listing_save_uploaded_photos($_FILES['photos'] ?? [], (int) $user['id']);
            $photos = cx_listing_photos_finalize([], $newSaved, $_POST);
            if (($resolved['veh'] ?? '') === 'otomobil') {
                $expertiseNew = cx_listing_save_uploaded_expertise($_FILES['expertise_photos'] ?? [], (int) $user['id']);
                $expertisePack = cx_listing_expertise_from_post($_POST, [], $expertiseNew);
                if ($expertisePack !== null) {
                    $attrs['expertise'] = $expertisePack;
                }
            }

            $category = $resolved['category'];
            $subcategory = $resolved['subcategory'];
            $priceTl = null;
            if ($mode === 'SALE') {
                if ($userIsKktc) {
                    $cur = strtoupper(trim((string) ($_POST['price_currency'] ?? 'GBP')));
                    if (!in_array($cur, ['GBP', 'TRY', 'EUR'], true)) {
                        $cur = 'GBP';
                    }
                    $amount = (float) ($_POST['price_amount'] ?? 0);
                    if ($amount > 0) {
                        $attrs['price'] = ['currency' => $cur, 'amount' => $amount];
                        if ($cur === 'TRY') {
                            $priceTl = $amount;
                        }
                    }
                } else {
                    $priceTl = (float) ($_POST['price_tl'] ?? 0);
                }
            }

            $qualityErr = cx_listing_quality_validate([
                'title' => trim((string) ($_POST['title'] ?? '')),
                'description' => trim((string) ($_POST['description'] ?? '')),
                'listing_mode' => $mode,
                'price_tl' => $priceTl,
                'price_amount' => $userIsKktc ? (float) ($_POST['price_amount'] ?? 0) : null,
                'photo_urls' => $photos,
                'attrs_json' => $attrs,
                'location' => trim((string) ($_POST['location'] ?? '')),
                'user_is_kktc' => $userIsKktc,
            ]);
            if ($qualityErr !== null) {
                $formError = $qualityErr;
                $cxPrefillCreateFromPost();
            } else {
            try {
                $writer = new ListingWriteService();
                $id = $writer->create((int) $user['id'], [
                'title' => trim((string) ($_POST['title'] ?? '')),
                'description' => trim((string) ($_POST['description'] ?? '')),
                'category' => $category,
                'subcategory' => $subcategory,
                'location' => trim((string) ($_POST['location'] ?? '')),
                'wanted_items' => trim((string) ($_POST['wanted_items'] ?? '')),
                'listing_mode' => $mode,
                'price_tl' => $priceTl,
                'price_negotiable' => !empty($_POST['price_negotiable']),
                'photo_urls' => $photos,
                'mandal_units' => (int) ($_POST['mandal_units'] ?? 10),
                'attrs_json' => $attrs,
            ]);
            cx_flash('ok', 'İlan oluşturuldu (#' . cx_listing_no($id) . '). Moderasyon onayı bekleniyor.');
            cx_redirect('/my-listings.php');
            } catch (Throwable $e) {
                $formError = $e->getMessage();
            }
            } // quality validate
            } // similar ack / create
        }
    }
    } // quota ok

    // Hata: kullanıcı girdilerini koru (vazgeçmesin)
    if ($formError !== null) {
        $cxPrefillCreateFromPost();
    }
}

ob_start();
?>
<h1 class="section-title">Araç ilanı ver</h1>
<p class="section-sub">Otomobil, motosiklet, bisiklet, ticari ve antika araç ilanları — kategori listesi ana sayfayla aynıdır.</p>

<div class="alert <?= $quota['ok'] ? 'alert-ok' : 'alert-error' ?>" style="margin-bottom:16px">
  <?= cx_e($quota['message']) ?>
  <?php if (!empty($quota['contact_admin'])): ?>
    <br><a class="link-gold" href="<?= cx_e(cx_admin_contact_href()) ?>">Admin ile iletişime geç</a>
  <?php elseif (!$quota['ok'] && cx_is_dealer($user)): ?>
    <br><span style="opacity:.85">Sınırsız ilan için admin’den <strong>VIP Kurumsal</strong> talep edin.</span>
  <?php elseif (!$quota['ok'] && !cx_is_dealer($user) && !cx_is_vip_kurumsal($user)): ?>
    <br><span style="opacity:.85">Daha fazla ilan için kurumsal (galeri) hesap talep edebilirsiniz — admin ile görüşün.</span>
    <a class="link-gold" href="<?= cx_e(cx_admin_contact_href()) ?>">İletişim</a>
  <?php endif; ?>
</div>

<?php if ($formError !== null): ?>
  <div class="alert alert-error"><?= cx_e($formError) ?></div>
<?php endif; ?>

<?php if ($needsSimilarAck): ?>
  <div class="alert alert-warn">
    Benzer özelliklerde başka ilanlar bulundu. Aşağıdaki listeyi kontrol edin; yine de göndermek için onay kutusunu işaretleyin.
  </div>
  <?php
    $similarMode = 'create';
    $uploadsUrl = $app['uploads_url'] ?? '/uploads';
    $siteUrl = (string) ($app['site_url'] ?? '');
    require __DIR__ . '/views/partials/similar-listings.php';
  ?>
<?php endif; ?>

<?php if (!$quota['ok']): ?>
<p class="empty-state"><a class="link-gold" href="/my-listings.php">İlanlarıma git</a></p>
<?php else: ?>

<form class="form create-listing-form" method="post" enctype="multipart/form-data" id="create_listing_form">
  <?= cx_csrf_field() ?>
  <label>Başlık</label>
  <input class="create-input" name="title" required maxlength="255" placeholder="Örn: Yamaha MT-07 2021 — 8.500 km" value="<?= cx_e($formTitle) ?>">

  <label>Açıklama</label>
  <textarea class="create-input create-input--area" name="description" rows="4" required minlength="10" maxlength="5000"><?= cx_e($formDescription) ?></textarea>
  <p class="muted" style="margin:4px 0 12px;font-size:12px">Klasik metni silebilirsiniz; en az 10 karakter yazın.</p>

  <label>Kategori</label>
  <select name="listing_subcat" id="listing_subcat" class="create-input" required>
    <option value="">Kategori seçin</option>
    <?php foreach (cx_listing_category_groups() as $parent => $items): ?>
      <optgroup label="<?= cx_e($parent) ?>">
        <?php foreach ($items as $item): ?>
          <?php $row = cx_marketplace_by_slug($item['slug']); ?>
          <option
            value="<?= cx_e($item['slug']) ?>"
            data-parent="<?= cx_e($parent) ?>"
            data-veh="<?= cx_e($row['veh'] ?? '') ?>"
            <?= $prefillSubcat === $item['slug'] ? ' selected' : '' ?>
          ><?= cx_e($item['label']) ?></option>
        <?php endforeach; ?>
      </optgroup>
    <?php endforeach; ?>
  </select>
  <p class="create-vehicle__hint">Otomobil · Motosiklet · Bisiklet · Ticari Araç · Antika Araç</p>

  <?php
    $showSteeringField = $userIsKktc;
    require __DIR__ . '/views/partials/create-vehicle-fields.php';
  ?>

  <div class="create-listing-step" data-listing-step="offer" hidden>
    <h3 class="create-listing-step__title">Satış / konum</h3>
    <label>Şehir</label>
    <?php if ($userIsKktc): ?>
      <?php require_once __DIR__ . '/app/Helpers/kktc-locations.php'; ?>
      <select class="create-input" name="location" required>
        <option value="">— Şehir seçin —</option>
        <?php foreach (cx_kktc_cities() as $code => $row): ?>
          <?php $cityLabel = (string) $row['label']; ?>
          <option value="<?= cx_e($cityLabel) ?>"<?= $formLocation === $cityLabel ? ' selected' : '' ?>><?= cx_e($cityLabel) ?></option>
        <?php endforeach; ?>
      </select>
    <?php else: ?>
    <input class="create-input" name="location" placeholder="İstanbul" value="<?= cx_e($formLocation) ?>">
    <?php endif; ?>

    <label>Mod</label>
    <select name="listing_mode" id="listing_mode" class="create-input">
      <option value="TRADE"<?= $formMode === 'TRADE' ? ' selected' : '' ?>>Takas</option>
      <option value="SALE"<?= $formMode === 'SALE' ? ' selected' : '' ?>><?= $userIsKktc ? 'Satılık (Sterlin / TL)' : 'Satılık (TL)' ?></option>
    </select>

    <div id="trade_fields"<?= $formMode === 'SALE' ? ' hidden' : '' ?>>
      <label>Takas isteği</label>
      <input class="create-input" name="wanted_items" placeholder="Örn: iPad Pro" value="<?= cx_e($formWanted) ?>">
    </div>

    <div id="sale_fields"<?= $formMode === 'SALE' ? '' : ' hidden' ?>>
      <?php if ($userIsKktc): ?>
      <label>Para birimi</label>
      <select name="price_currency" id="price_currency" class="create-input">
        <option value="GBP"<?= $formPriceCurrency === 'GBP' ? ' selected' : '' ?>>Sterlin (£)</option>
        <option value="TRY"<?= $formPriceCurrency === 'TRY' ? ' selected' : '' ?>>Türk Lirası (₺)</option>
      </select>
      <label>Fiyat</label>
      <input class="create-input" name="price_amount" type="number" min="1" step="1" placeholder="Örn: 12500" value="<?= cx_e($formPriceAmount) ?>" data-quality-price>
      <input type="hidden" name="price_tl" id="price_tl_hidden" value="">
      <?php else: ?>
      <label>Fiyat (TL)</label>
      <input class="create-input" name="price_tl" type="number" min="1" step="1" value="<?= cx_e($formPriceTl) ?>" data-quality-price>
      <?php endif; ?>
      <label class="create-check"><input type="checkbox" name="price_negotiable" value="1"<?= $formPriceNegotiable ? ' checked' : '' ?>> Pazarlık yapılır</label>
    </div>
  </div>

  <div class="create-listing-step" data-listing-step="media" hidden>
    <h3 class="create-listing-step__title">Fotoğraf<span data-expertise-title-bit> & ekspertiz</span></h3>
    <?php
      $uploadInputId = 'create_listing_photos';
      $uploadLabel = 'Fotograflar';
      require __DIR__ . '/views/partials/listing-photo-upload.php';
    ?>

    <div data-expertise-otomobil-only<?= ($prefillSegment !== '' && $prefillSegment !== 'otomobil') ? ' hidden' : '' ?>>
    <?php
      $expertiseStubs = [];
      $expertiseParts = $expertisePartsPrefill;
      require __DIR__ . '/views/partials/expertise-upload.php';
    ?>
    </div>

    <?php if ($formError !== null || $needsSimilarAck): ?>
      <p class="create-vehicle__hint">Not: Tekrar göndermeden önce fotoğrafları<span data-expertise-title-bit> ve ekspertiz sayfalarını</span> yeniden seçmeniz gerekir.</p>
    <?php endif; ?>
  </div>

  <div class="create-listing-step" data-listing-step="submit" hidden>
    <?php if (cx_listing_quality_enabled()): ?>
      <?php
        $qualityPanelMode = 'create';
        $qualityMinPhotos = cx_listing_quality_settings()['min_photos'];
        require __DIR__ . '/views/partials/listing-quality-panel.php';
      ?>
    <?php endif; ?>

    <?php if ($needsSimilarAck): ?>
      <label class="create-check similar-listings__ack">
        <input type="checkbox" name="ack_similar" value="1" required>
        Benzer ilanları gördüm, yine de gönder
      </label>
    <?php endif; ?>

    <button class="btn-primary" type="submit"><?= $needsSimilarAck ? 'Yine de ilan oluştur' : 'İlan oluştur' ?></button>
  </div>
</form>

<script>
window.cxVehicleFormPrefill = <?= json_encode($prefillForm, JSON_UNESCAPED_UNICODE) ?>;
</script>
<script src="/assets/vehicle-form.js?v=3"></script>
<script src="/assets/expertise-diagram.js?v=5"></script>
<script src="/assets/listing-photos.js?v=1"></script>
<?php if (cx_listing_quality_enabled()): ?>
<script>
window.cxListingQuality = <?= json_encode(cx_listing_quality_settings(), JSON_UNESCAPED_UNICODE) ?>;
</script>
<script src="/assets/create-listing-quality.js?v=2"></script>
<?php endif; ?>
<script>
(function () {
  var modeSel = document.getElementById('listing_mode');
  if (!modeSel) return;
  var saleFields = document.getElementById('sale_fields');
  var tradeFields = document.getElementById('trade_fields');
  var segmentSel = document.getElementById('vehicle_segment');
  var subcatSel = document.getElementById('listing_subcat');
  var expertiseBox = document.querySelector('[data-expertise-otomobil-only]');
  var expertiseBits = document.querySelectorAll('[data-expertise-title-bit]');

  function syncExpertiseVisibility() {
    var isCar = segmentSel && segmentSel.value === 'otomobil';
    if (expertiseBox) expertiseBox.hidden = !isCar;
    expertiseBits.forEach(function (el) { el.hidden = !isCar; });
  }

  function toggleMode() {
    var sale = modeSel.value === 'SALE';
    saleFields.hidden = !sale;
    tradeFields.hidden = sale;
  }

  modeSel.addEventListener('change', toggleMode);
  if (subcatSel && subcatSel.value) {
    var initialOpt = subcatSel.options[subcatSel.selectedIndex];
    if (segmentSel && initialOpt) {
      segmentSel.value = initialOpt.getAttribute('data-veh') || '';
    }
  }
  if (subcatSel) {
    subcatSel.addEventListener('change', function () {
      var opt = subcatSel.options[subcatSel.selectedIndex];
      if (segmentSel && opt) {
        segmentSel.value = opt.getAttribute('data-veh') || '';
      }
      syncExpertiseVisibility();
    });
  }
  if (segmentSel) {
    segmentSel.addEventListener('change', syncExpertiseVisibility);
  }
  toggleMode();
  syncExpertiseVisibility();
})();
</script>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'İlan oluştur';
$layout = 'app';
$navActive = 'create';
require __DIR__ . '/views/layout.php';
