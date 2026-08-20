<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/UserAdminService.php';
require_once dirname(__DIR__) . '/app/Services/AdminListingService.php';

use App\Helpers\Security;
use App\Services\AdminListingService;
use App\Services\UserAdminService;

cx_bootstrap();
$user = cx_require_staff();

$id = (int) ($_GET['id'] ?? 0);
$svc = new AdminListingService();
$item = $svc->find($id);

if ($item === null) {
    cx_flash('error', 'İlan bulunamadı.');
    cx_redirect('/admin/');
}

$formError = null;
$subcatSlug = '';
$prefillSegment = '';
$attrsDecoded = null;
if (!empty($item['attrs_json'])) {
    $decoded = json_decode((string) $item['attrs_json'], true);
    if (is_array($decoded)) {
        $attrsDecoded = $decoded;
    }
}
foreach (cx_marketplace_catalog() as $row) {
    if ($row['label'] === ($item['subcategory'] ?? '')) {
        $subcatSlug = $row['slug'];
        $prefillSegment = (string) ($row['veh'] ?? '');
        break;
    }
}
$prefillForm = cx_vehicle_form_values_from_attrs($attrsDecoded);
if ($prefillSegment !== '' && ($prefillForm['vehicle_segment'] ?? '') === '') {
    $prefillForm['vehicle_segment'] = $prefillSegment;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    Security::rateLimit('admin_listing_edit', 80, 300);
    try {
        if (isset($_POST['quick_decision'])) {
            $dec = strtoupper((string) $_POST['quick_decision']);
            $map = ['APPROVE' => 'APPROVED', 'REJECT' => 'REJECTED'];
            if (isset($map[$dec])) {
                $reason = trim((string) ($_POST['reject_reason'] ?? ''));
                $svc->setStatus($id, $map[$dec], $user, $reason);
                cx_flash('ok', 'Durum güncellendi: ' . cx_listing_status_label($map[$dec]));
                cx_redirect('/admin/listing-edit.php?id=' . $id);
            }
        }

        $data = $_POST;
        if (!empty($_POST['save_and_approve'])) {
            $data['status'] = 'APPROVED';
        }
        $svc->update($id, $data, $user);
        cx_flash('ok', 'İlan #' . cx_listing_no($id) . ' kaydedildi.');
        cx_redirect('/admin/listing-edit.php?id=' . $id);
    } catch (Throwable $e) {
        $formError = $e->getMessage();
        $item = array_merge($item, [
            'title' => $_POST['title'] ?? $item['title'],
            'description' => $_POST['description'] ?? $item['description'],
            'location' => $_POST['location'] ?? $item['location'],
            'wanted_items' => $_POST['wanted_items'] ?? $item['wanted_items'],
            'listing_mode' => $_POST['listing_mode'] ?? $item['listing_mode'],
            'price_tl' => $_POST['price_tl'] ?? $item['price_tl'],
            'status' => $_POST['status'] ?? $item['status'],
        ]);
        $subcatSlug = trim((string) ($_POST['listing_subcat'] ?? $subcatSlug));
        $resolvedErr = cx_resolve_listing_category($subcatSlug);
        $prefillSegment = (string) ($resolvedErr['veh'] ?? $prefillSegment);
        $prefillForm = cx_vehicle_form_values_from_attrs(null);
        foreach ($_POST as $k => $v) {
            if (is_string($v) && (str_starts_with($k, 'vehicle_') || in_array($k, ['seller_type', 'seller_phone', 'seller_website'], true))) {
                $prefillForm[$k] = $v;
            }
        }
        if ($prefillSegment !== '') {
            $prefillForm['vehicle_segment'] = $prefillSegment;
        }
    }
}

$photoStubs = cx_listing_photo_stubs($item['photo_urls'] ?? '[]');
$coverStub = $photoStubs[0] ?? '';
$photosText = trim((string) ($_POST['photo_urls_text'] ?? ''));
$prefillMake = trim((string) ($prefillForm['vehicle_make'] ?? ''));
$prefillModel = trim((string) ($prefillForm['vehicle_model'] ?? ''));
if ($prefillModel !== '' && $prefillSegment !== '' && $prefillMake !== ''
    && !cx_vehicle_model_in_catalog($prefillModel, $prefillSegment, $prefillMake)) {
    $prefillForm['vehicle_model_custom'] = $prefillModel;
    $prefillForm['vehicle_model'] = cx_vehicle_model_custom_option();
}

$similarListings = [];
if (is_array($attrsDecoded)) {
    $similarListings = cx_listing_find_similar(
        $attrsDecoded,
        $id,
        8,
        (int) ($item['owner_id'] ?? 0)
    );
}
$attrsText = '';
if (!empty($item['attrs_json'])) {
    $decoded = json_decode((string) $item['attrs_json'], true);
    $attrsText = json_encode($decoded, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) ?: (string) $item['attrs_json'];
}

$adminTab = 'listings';
ob_start();
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<div class="admin-edit-head">
  <a class="admin-back" href="/admin/">← İlan listesi</a>
  <div class="admin-edit-head__meta">
    <span class="admin-row__no">#<?= (int) ($item['listing_no'] ?? cx_listing_no($id)) ?></span>
    <span class="admin-badge admin-badge--<?= cx_e(cx_listing_status_class((string) $item['status'])) ?>">
      <?= cx_e(cx_listing_status_label((string) $item['status'])) ?>
    </span>
  </div>
</div>

<?php if ($formError !== null): ?>
  <div class="alert alert-error"><?= cx_e($formError) ?></div>
<?php endif; ?>

<?php if ($similarListings !== []): ?>
  <div class="alert alert-warn">
    Benzer özelliklerde <?= count($similarListings) ?> ilan bulundu. Aşağıdakileri kontrol edin; yine de onaylayabilirsiniz.
  </div>
  <?php
    $similarMode = 'admin';
    $appCfg = cx_app_config();
    $uploadsUrl = $appCfg['uploads_url'] ?? '/uploads';
    $siteUrl = (string) ($appCfg['site_url'] ?? '');
    require dirname(__DIR__) . '/views/partials/similar-listings.php';
  ?>
<?php endif; ?>

<?php if (cx_listing_quality_enabled()): ?>
  <?php
    $adminQuality = cx_listing_quality_assess([
        'title' => (string) ($item['title'] ?? ''),
        'description' => (string) ($item['description'] ?? ''),
        'listing_mode' => (string) ($item['listing_mode'] ?? 'TRADE'),
        'price_tl' => $item['price_tl'] ?? null,
        'photo_urls' => $item['photo_urls'] ?? '[]',
        'attrs_json' => is_array($attrsDecoded) ? $attrsDecoded : [],
        'location' => (string) ($item['location'] ?? ''),
        'user_is_kktc' => false,
    ]);
    $adminQClass = cx_listing_quality_score_class((int) $adminQuality['score']);
  ?>
  <div class="admin-quality-panel admin-quality-panel--<?= cx_e($adminQClass) ?>">
    <strong>Kalite skoru: <?= (int) $adminQuality['score'] ?>/100</strong>
    <?php if ($adminQuality['issues'] !== []): ?>
      <ul class="admin-quality-panel__issues">
        <?php foreach ($adminQuality['issues'] as $issue): ?>
          <li><?= cx_e($issue) ?></li>
        <?php endforeach; ?>
      </ul>
    <?php else: ?>
      <p class="admin-quality-panel__ok">Temel kalite kriterleri karsilaniyor.</p>
    <?php endif; ?>
  </div>
<?php endif; ?>

<form class="admin-edit" method="post">
  <?= cx_csrf_field() ?>

  <div class="admin-edit__layout">
    <aside class="admin-edit__gallery">
      <h3 class="admin-edit__side-title">Gorseller</h3>
      <?php require dirname(__DIR__) . '/views/partials/listing-photo-editor.php'; ?>
      <details class="admin-edit__advanced" style="margin-top:12px">
        <summary>URL ile duzenle (gelismis)</summary>
        <label class="admin-edit__label">Foto URL (satir satir)</label>
        <textarea class="admin-edit__textarea" name="photo_urls_text" rows="5" placeholder="https://…"><?= cx_e($photosText) ?></textarea>
        <p class="admin-edit__hint">× ile kaldirin. URL alanini yalnizca toplu yapistirmak icin kullanin; doldurursaniz galeri yerine o liste kaydedilir.</p>
      </details>

      <div class="admin-edit__owner">
        <strong>Sahip</strong>
        <div>@<?= cx_e($item['owner_username'] ?? '') ?></div>
        <?php if (!empty($item['owner_email'])): ?>
          <div class="admin-edit__muted"><?= cx_e($item['owner_email']) ?></div>
        <?php endif; ?>
      </div>
    </aside>

    <div class="admin-edit__main">
      <div class="admin-edit__grid">
        <label class="admin-edit__field admin-edit__field--wide">
          <span>Başlık</span>
          <input class="admin-edit__input" name="title" required maxlength="255" value="<?= cx_e((string) $item['title']) ?>">
        </label>

        <label class="admin-edit__field admin-edit__field--wide">
          <span>Açıklama</span>
          <textarea class="admin-edit__textarea" name="description" rows="6" required minlength="10"><?= cx_e((string) $item['description']) ?></textarea>
        </label>

        <label class="admin-edit__field">
          <span>Kategori</span>
          <select class="admin-edit__input" name="listing_subcat" id="listing_subcat" required>
            <?php foreach (cx_listing_category_groups() as $parent => $items): ?>
              <optgroup label="<?= cx_e($parent) ?>">
                <?php foreach ($items as $cat): ?>
                  <?php $catRow = cx_marketplace_by_slug($cat['slug']); ?>
                  <option
                    value="<?= cx_e($cat['slug']) ?>"
                    data-veh="<?= cx_e($catRow['veh'] ?? '') ?>"
                    <?= $subcatSlug === $cat['slug'] ? ' selected' : '' ?>
                  >
                    <?= cx_e($cat['label']) ?>
                  </option>
                <?php endforeach; ?>
              </optgroup>
            <?php endforeach; ?>
          </select>
        </label>

        <label class="admin-edit__field">
          <span>Durum</span>
          <select class="admin-edit__input" name="status">
            <?php
              $statusOptions = [
                  'PENDING_MODERATION' => 'Onay Bekliyor',
                  'APPROVED' => 'Onaylı',
                  'ACTIVE' => 'Yayında',
                  'SOLD' => 'Satıldı',
                  'REJECTED' => 'Reddedildi',
                  'CANCELLED' => 'Silindi',
              ];
              foreach (cx_staff_allowed_statuses($user) as $val):
                  if (!isset($statusOptions[$val])) {
                      continue;
                  }
                  $lbl = $statusOptions[$val];
            ?>
              <option value="<?= cx_e($val) ?>"<?= strtoupper((string) $item['status']) === $val ? ' selected' : '' ?>><?= cx_e($lbl) ?></option>
            <?php endforeach; ?>
          </select>
        </label>

        <label class="admin-edit__field">
          <span>Şehir</span>
          <input class="admin-edit__input" name="location" value="<?= cx_e((string) ($item['location'] ?? '')) ?>">
        </label>

        <label class="admin-edit__field">
          <span>Mod</span>
          <select class="admin-edit__input" name="listing_mode" id="listing_mode">
            <option value="TRADE"<?= strtoupper((string) ($item['listing_mode'] ?? '')) === 'TRADE' ? ' selected' : '' ?>>Takas</option>
            <option value="SALE"<?= strtoupper((string) ($item['listing_mode'] ?? '')) === 'SALE' ? ' selected' : '' ?>>Satılık</option>
          </select>
        </label>

        <label class="admin-edit__field" id="price_wrap">
          <span>Fiyat (TL)</span>
          <input class="admin-edit__input" type="number" name="price_tl" min="0" step="1" value="<?= cx_e((string) ($item['price_tl'] ?? '')) ?>">
        </label>

        <label class="admin-edit__field admin-edit__check">
          <input type="checkbox" name="price_negotiable" value="1"<?= !empty($item['price_negotiable']) ? ' checked' : '' ?>>
          <span>Pazarlık yapılır</span>
        </label>

        <label class="admin-edit__field admin-edit__field--wide">
          <span>Ret nedeni (Reddet’te kullanıcıya bildirim olarak gider)</span>
          <input class="admin-edit__input" type="text" name="reject_reason" maxlength="500"
                 placeholder="Örn. Fotoğraflar yetersiz / fiyat hatalı / açıklama eksik"
                 value="<?= cx_e(trim((string) ($_POST['reject_reason'] ?? ($item['moderation_reason'] ?? '')))) ?>">
        </label>

        <label class="admin-edit__field admin-edit__field--wide">
          <span>Takas isteği</span>
          <input class="admin-edit__input" name="wanted_items" value="<?= cx_e((string) ($item['wanted_items'] ?? '')) ?>">
        </label>

        <div class="admin-edit__field admin-edit__field--wide admin-edit__vehicle-wrap">
          <?php $vehicleFormRelaxed = true; require dirname(__DIR__) . '/views/partials/create-vehicle-fields.php'; ?>
        </div>

        <details class="admin-edit__field admin-edit__field--wide admin-edit__advanced">
          <summary>Gelişmiş — attrs_json (isteğe bağlı)</summary>
          <textarea class="admin-edit__textarea admin-edit__textarea--code" name="attrs_json_text" rows="8" placeholder='{"segment":"otomobil","vehicle":{…}}'><?= cx_e($attrsText) ?></textarea>
          <p class="admin-edit__hint">Marka/model alanları kaydedildiğinde JSON otomatik güncellenir. Yalnızca gelişmiş düzenleme için kullanın.</p>
        </details>
      </div>

      <div class="admin-edit__actions">
        <button class="admin-btn admin-btn--primary" type="submit" name="save" value="1">Kaydet</button>
        <button class="admin-btn admin-btn--ok" type="submit" name="save_and_approve" value="1">Kaydet ve onayla</button>
        <?php if (!in_array(strtoupper((string) $item['status']), ['APPROVED', 'ACTIVE'], true)): ?>
          <button class="admin-btn admin-btn--ok" type="submit" name="quick_decision" value="APPROVE">Hızlı onay</button>
        <?php endif; ?>
        <button class="admin-btn admin-btn--warn" type="submit" name="quick_decision" value="REJECT"
                onclick="return window.cxAdminRejectReason(this.form)">Reddet</button>
        <a class="admin-btn" href="/listing.php?id=<?= $id ?>" target="_blank" rel="noopener">Canlı önizle</a>
        <a class="admin-btn admin-btn--gold" href="/share-card.php?id=<?= $id ?>" target="_blank" rel="noopener">Instagram kartı</a>
      </div>
    </div>
  </div>
</form>

<script>
window.cxVehicleFormPrefill = <?= json_encode($prefillForm, JSON_UNESCAPED_UNICODE) ?>;
</script>
<script src="/assets/vehicle-form.js?v=3"></script>
<script src="/assets/listing-photos.js?v=1"></script>
<script>
(function () {
  var mode = document.getElementById('listing_mode');
  var priceWrap = document.getElementById('price_wrap');
  function syncMode() {
    if (priceWrap) priceWrap.hidden = mode.value !== 'SALE';
  }
  mode && mode.addEventListener('change', syncMode);
  syncMode();
})();
</script>

<?php require dirname(__DIR__) . '/views/partials/admin-reject-reason.php'; ?>

<?php
$content = ob_get_clean();
$title = 'İlan düzenle';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
