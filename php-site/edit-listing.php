<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingWriteService.php';

use App\Helpers\Database;
use App\Helpers\Security;
use App\Services\ListingWriteService;

cx_bootstrap();
$user = cx_require_user();
$app = cx_app_config();
$userIsKktc = cx_user_is_kktc($user);
$id = (int) ($_GET['id'] ?? 0);
if ($id <= 0) {
    cx_redirect('/my-listings.php');
}

$pdo = Database::pdo();
$stmt = $pdo->prepare('SELECT * FROM trade_listings WHERE id = ? AND owner_id = ? LIMIT 1');
$stmt->execute([$id, (int) $user['id']]);
$listing = $stmt->fetch();
if (!$listing) {
    cx_flash('error', 'Ilan bulunamadi veya size ait degil.');
    cx_redirect('/my-listings.php');
}

$status = strtoupper((string) ($listing['status'] ?? ''));
if ($status === 'CANCELLED') {
    cx_flash('error', 'Iptal edilmis ilan duzenlenemez.');
    cx_redirect('/my-listings.php');
}

$subcatSlug = '';
$prefillSegment = '';
$attrsDecoded = null;
if (!empty($listing['attrs_json'])) {
    $decoded = json_decode((string) $listing['attrs_json'], true);
    if (is_array($decoded)) {
        $attrsDecoded = $decoded;
    }
}
foreach (cx_marketplace_catalog() as $row) {
    if ($row['label'] === ($listing['subcategory'] ?? '')) {
        $subcatSlug = $row['slug'];
        $prefillSegment = (string) ($row['veh'] ?? '');
        break;
    }
}
$prefillForm = cx_vehicle_form_values_from_attrs($attrsDecoded);
if ($prefillSegment !== '' && ($prefillForm['vehicle_segment'] ?? '') === '') {
    $prefillForm['vehicle_segment'] = $prefillSegment;
}

$formError = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::rateLimit('edit_listing', 20, 300);
    Security::requireCsrf();

    $mode = strtoupper(trim((string) ($_POST['listing_mode'] ?? 'TRADE')));
    $existingPhotos = cx_listing_photo_stubs($listing['photo_urls'] ?? '[]');
    $kept = isset($_POST['photo_editor'])
        ? cx_listing_photos_from_keep($_POST, $existingPhotos)
        : $existingPhotos;
    $newSaved = cx_listing_save_uploaded_photos($_FILES['photos'] ?? [], (int) $user['id']);
    $photos = cx_listing_photos_finalize($kept, $newSaved, $_POST);

    $subcatSlugPost = trim((string) ($_POST['listing_subcat'] ?? ''));
    $resolved = cx_resolve_listing_category($subcatSlugPost);
    if ($resolved === null) {
        $formError = 'Gecerli bir kategori secin.';
    } else {
        $post = $_POST;
        $post['vehicle_segment'] = $resolved['veh'];
        if ($userIsKktc && in_array($resolved['veh'], ['otomobil', 'motosiklet', 'ticari', 'antika-arac'], true)) {
            $post['require_steering'] = '1';
        }
        if (cx_listing_quality_enabled()) {
            $vehiclePack = cx_vehicle_attrs_from_post($post);
        } else {
            $vehiclePack = cx_vehicle_attrs_merge_admin($post, $attrsDecoded);
        }
        if ($vehiclePack['error'] !== null) {
            $formError = $vehiclePack['error'];
        } elseif ($vehiclePack['attrs'] === null) {
            $formError = cx_listing_quality_enabled()
                ? 'Arac teknik bilgilerini doldurun.'
                : 'Arac markasi secin.';
        } else {
            $attrsOut = $vehiclePack['attrs'];
            if ($mode === 'SALE') {
                if ($userIsKktc) {
                    $cur = strtoupper(trim((string) ($_POST['price_currency'] ?? 'GBP')));
                    if (!in_array($cur, ['GBP', 'TRY', 'EUR'], true)) {
                        $cur = 'GBP';
                    }
                    $amount = (float) ($_POST['price_amount'] ?? 0);
                    if ($amount > 0) {
                        $attrsOut['price'] = ['currency' => $cur, 'amount' => $amount];
                    } else {
                        unset($attrsOut['price']);
                    }
                }
            }
            if (($resolved['veh'] ?? '') === 'otomobil') {
                $existingExpertise = cx_listing_expertise($listing);
                $keptExpertise = cx_listing_expertise_kept_from_post($_POST, $existingExpertise['photos']);
                $expertiseNew = cx_listing_save_uploaded_expertise($_FILES['expertise_photos'] ?? [], (int) $user['id']);
                $expertisePack = cx_listing_expertise_from_post($_POST, $keptExpertise, $expertiseNew);
                if ($expertisePack !== null) {
                    $attrsOut['expertise'] = $expertisePack;
                } else {
                    unset($attrsOut['expertise']);
                }
            } else {
                unset($attrsOut['expertise']);
            }

            $priceTl = $mode === 'SALE' ? (float) ($_POST['price_tl'] ?? 0) : null;
            $qualityErr = cx_listing_quality_validate([
                'title' => trim((string) ($_POST['title'] ?? '')),
                'description' => trim((string) ($_POST['description'] ?? '')),
                'listing_mode' => $mode,
                'price_tl' => $priceTl,
                'price_amount' => $userIsKktc ? (float) ($_POST['price_amount'] ?? 0) : null,
                'photo_urls' => $photos,
                'attrs_json' => $attrsOut,
                'location' => trim((string) ($_POST['location'] ?? '')),
                'user_is_kktc' => $userIsKktc,
            ]);
            if ($qualityErr !== null) {
                $formError = $qualityErr;
            } else {
            try {
                $writer = new ListingWriteService();
                $writer->updateForOwner($id, (int) $user['id'], [
                    'title' => trim((string) ($_POST['title'] ?? '')),
                    'description' => trim((string) ($_POST['description'] ?? '')),
                    'category' => $resolved['category'],
                    'subcategory' => $resolved['subcategory'],
                    'location' => trim((string) ($_POST['location'] ?? '')),
                    'wanted_items' => trim((string) ($_POST['wanted_items'] ?? '')),
                    'listing_mode' => $mode,
                    'price_tl' => $priceTl,
                    'price_negotiable' => !empty($_POST['price_negotiable']),
                    'photo_urls' => $photos,
                    'attrs_json' => $attrsOut,
                ]);
                cx_flash('ok', 'Ilan guncellendi. Moderasyon onayi gerekebilir.');
                cx_redirect('/my-listings.php');
            } catch (Throwable $e) {
                $formError = $e->getMessage();
            }
            }
        }
    }
}

$listingMode = strtoupper((string) ($listing['listing_mode'] ?? 'TRADE'));
$vehicleFormRelaxed = !cx_listing_quality_enabled();
$photoStubs = cx_listing_photo_stubs($listing['photo_urls'] ?? '[]');
$existingPhotoCount = count($photoStubs);
$coverStub = $photoStubs[0] ?? '';
$prefillMake = trim((string) ($prefillForm['vehicle_make'] ?? ''));
$prefillModel = trim((string) ($prefillForm['vehicle_model'] ?? ''));
if ($prefillModel !== '' && $prefillSegment !== '' && $prefillMake !== ''
    && !cx_vehicle_model_in_catalog($prefillModel, $prefillSegment, $prefillMake)) {
    $prefillForm['vehicle_model_custom'] = $prefillModel;
    $prefillForm['vehicle_model'] = cx_vehicle_model_custom_option();
}

ob_start();
?>
<p><a class="link-gold" href="/my-listings.php">← Ilanlarim</a></p>
<h1 class="section-title">Ilan duzenle</h1>
<p class="section-sub">Durum: <strong><?= cx_e(cx_listing_status_label($status)) ?></strong>
  <?php if (in_array($status, ['APPROVED', 'ACTIVE'], true)): ?>
    — Kaydettiginizde tekrar moderasyon bekler.
  <?php endif; ?>
</p>

<?php if ($formError !== null): ?>
  <div class="alert alert-error"><?= cx_e($formError) ?></div>
<?php endif; ?>

<form class="form create-listing-form" method="post" enctype="multipart/form-data">
  <?= cx_csrf_field() ?>
  <label>Baslik</label>
  <input class="create-input" name="title" required maxlength="255" value="<?= cx_e((string) ($listing['title'] ?? '')) ?>">

  <label>Aciklama</label>
  <?php
    $editDesc = trim((string) ($listing['description'] ?? ''));
    if ($editDesc === '') {
        $editDesc = cx_listing_default_description();
    }
  ?>
  <textarea class="create-input create-input--area" name="description" rows="4" required minlength="10" maxlength="5000"><?= cx_e($editDesc) ?></textarea>
  <p class="muted" style="margin:4px 0 12px;font-size:12px">Klasik metni silebilirsiniz; en az 10 karakter yazın.</p>

  <label>Kategori</label>
  <select name="listing_subcat" id="listing_subcat" class="create-input" required>
    <option value="">Kategori secin</option>
    <?php foreach (cx_listing_category_groups() as $parent => $items): ?>
      <optgroup label="<?= cx_e($parent) ?>">
        <?php foreach ($items as $item): ?>
          <?php $row = cx_marketplace_by_slug($item['slug']); ?>
          <option
            value="<?= cx_e($item['slug']) ?>"
            data-veh="<?= cx_e($row['veh'] ?? '') ?>"
            <?= $subcatSlug === $item['slug'] ? ' selected' : '' ?>
          ><?= cx_e($item['label']) ?></option>
        <?php endforeach; ?>
      </optgroup>
    <?php endforeach; ?>
  </select>

  <?php
    $showSteeringField = $userIsKktc;
    require __DIR__ . '/views/partials/create-vehicle-fields.php';
  ?>

  <label>Sehir</label>
  <?php if ($userIsKktc): ?>
    <?php require_once __DIR__ . '/app/Helpers/kktc-locations.php'; ?>
    <select class="create-input" name="location" required>
      <option value="">— Sehir secin —</option>
      <?php foreach (cx_kktc_cities() as $code => $row): ?>
        <?php $cityLabel = (string) $row['label']; ?>
        <option value="<?= cx_e($cityLabel) ?>"<?= ((string) ($listing['location'] ?? '') === $cityLabel) ? ' selected' : '' ?>><?= cx_e($cityLabel) ?></option>
      <?php endforeach; ?>
    </select>
  <?php else: ?>
  <input class="create-input" name="location" value="<?= cx_e((string) ($listing['location'] ?? '')) ?>">
  <?php endif; ?>

  <label>Mod</label>
  <select name="listing_mode" id="listing_mode" class="create-input">
    <option value="TRADE"<?= $listingMode === 'TRADE' ? ' selected' : '' ?>>Takas</option>
    <option value="SALE"<?= $listingMode === 'SALE' ? ' selected' : '' ?>>Satilik (TL)</option>
  </select>

  <div id="trade_fields"<?= $listingMode === 'SALE' ? ' hidden' : '' ?>>
    <label>Takas istegi</label>
    <input class="create-input" name="wanted_items" value="<?= cx_e((string) ($listing['wanted_items'] ?? '')) ?>">
  </div>

  <div id="sale_fields"<?= $listingMode !== 'SALE' ? ' hidden' : '' ?>>
    <?php
      $fx = cx_listing_price_currency($listing);
      $editPriceAmount = $fx !== null ? (string) (int) $fx['amount'] : '';
      $editPriceCurrency = $fx['currency'] ?? 'GBP';
    ?>
    <?php if ($userIsKktc): ?>
    <label>Para birimi</label>
    <select name="price_currency" class="create-input">
      <option value="GBP"<?= $editPriceCurrency === 'GBP' ? ' selected' : '' ?>>Sterlin (£)</option>
      <option value="TRY"<?= $editPriceCurrency === 'TRY' ? ' selected' : '' ?>>Turk Lirasi (₺)</option>
      <option value="EUR"<?= $editPriceCurrency === 'EUR' ? ' selected' : '' ?>>Euro (€)</option>
    </select>
    <label>Fiyat</label>
    <input class="create-input" name="price_amount" type="number" min="1" step="1" value="<?= cx_e($editPriceAmount) ?>" data-quality-price>
    <input type="hidden" name="price_tl" value="<?= cx_e((string) ($listing['price_tl'] ?? '')) ?>">
    <?php else: ?>
    <label>Fiyat (TL)</label>
    <input class="create-input" name="price_tl" type="number" min="1" step="1" value="<?= cx_e((string) ($listing['price_tl'] ?? '')) ?>" data-quality-price>
    <?php endif; ?>
    <label class="create-check"><input type="checkbox" name="price_negotiable" value="1"<?= !empty($listing['price_negotiable']) ? ' checked' : '' ?>> Pazarlik yapilir</label>
  </div>

  <label>Mevcut fotograflar</label>
  <?php require __DIR__ . '/views/partials/listing-photo-editor.php'; ?>

  <?php
    $uploadInputId = 'edit_listing_photos';
    $uploadLabel = 'Yeni fotograf ekle';
    require __DIR__ . '/views/partials/listing-photo-upload.php';
  ?>

  <?php
    $editSegment = (string) ($prefillForm['vehicle_segment'] ?? $prefillSegment ?? '');
    if ($editSegment === 'otomobil'):
      $expertiseInfo = cx_listing_expertise($listing);
      $expertiseHas = $expertiseInfo['has_report'];
      $expertiseStubs = $expertiseInfo['photos'];
      $expertiseParts = $expertiseInfo['parts'] ?? [];
      $uploadsUrl = $app['uploads_url'] ?? '/uploads';
      $siteUrl = (string) ($app['url'] ?? '');
      require __DIR__ . '/views/partials/expertise-upload.php';
    endif;
  ?>

  <?php if (cx_listing_quality_enabled()): ?>
    <?php
      $qualityPanelMode = 'edit';
      $qualityMinPhotos = cx_listing_quality_settings()['min_photos'];
      require __DIR__ . '/views/partials/listing-quality-panel.php';
    ?>
  <?php endif; ?>

  <button class="btn-primary" type="submit">Kaydet</button>
</form>

<script>
window.cxVehicleFormPrefill = <?= json_encode($prefillForm, JSON_UNESCAPED_UNICODE) ?>;
</script>
<script src="/assets/vehicle-form.js?v=3"></script>
<?php if (($prefillForm['vehicle_segment'] ?? $prefillSegment ?? '') === 'otomobil'): ?>
<script src="/assets/expertise-diagram.js?v=5"></script>
<?php endif; ?>
<script src="/assets/listing-photos.js?v=1"></script>
<?php if (cx_listing_quality_enabled()): ?>
<script>
window.cxListingQuality = <?= json_encode(array_merge(cx_listing_quality_settings(), ['existing_photos' => $existingPhotoCount]), JSON_UNESCAPED_UNICODE) ?>;
</script>
<script src="/assets/create-listing-quality.js?v=2"></script>
<?php endif; ?>
<script>
(function () {
  var modeSel = document.getElementById('listing_mode');
  var saleFields = document.getElementById('sale_fields');
  var tradeFields = document.getElementById('trade_fields');
  if (!modeSel) return;
  modeSel.addEventListener('change', function () {
    var sale = modeSel.value === 'SALE';
    saleFields.hidden = !sale;
    tradeFields.hidden = sale;
  });
})();
</script>
<?php
$content = ob_get_clean();
$title = 'Ilan duzenle';
$layout = 'app';
$navActive = 'mine';
require __DIR__ . '/views/layout.php';
