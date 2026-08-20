<?php

declare(strict_types=1);

/** @var bool $expertiseHas */
/** @var list<string> $expertiseStubs */
/** @var array<string,string> $expertiseParts */
/** @var string $uploadsUrl */
/** @var string $siteUrl */

$expertiseHas = !empty($expertiseHas);
$expertiseStubs = $expertiseStubs ?? [];
$expertiseParts = is_array($expertiseParts ?? null) ? $expertiseParts : [];
$uploadsUrl = $uploadsUrl ?? (cx_app_config()['uploads_url'] ?? '/uploads');
$siteUrl = $siteUrl ?? (string) (cx_app_config()['site_url'] ?? cx_app_config()['url'] ?? '');
?>
<div class="expertise-upload" data-expertise-upload>
  <label class="create-check">
    <input type="checkbox" name="expertise_has" value="1" id="expertise_has"<?= $expertiseHas || $expertiseParts !== [] ? ' checked' : '' ?>>
    Ekspertiz / kaporta durumunu belirttim
  </label>
  <p class="create-vehicle__hint">Aşağıdaki şemada parçaya tıklayıp durum seçin. İsterseniz ekspertiz raporu fotoğrafı da ekleyebilirsiniz.</p>

  <?php
    $expertiseReadonly = false;
    require __DIR__ . '/expertise-diagram.php';
  ?>

  <details class="expertise-upload__photos">
    <summary>Rapor fotoğrafı yükle (opsiyonel)</summary>
    <?php if ($expertiseStubs !== []): ?>
    <div class="expertise-upload__existing">
      <span class="expertise-upload__label">Mevcut rapor sayfaları</span>
      <div class="expertise-upload__grid">
        <?php foreach ($expertiseStubs as $stub): ?>
          <?php $display = cx_photo_urls([$stub], $uploadsUrl)[0] ?? ''; ?>
          <label class="expertise-upload__item">
            <input type="checkbox" name="keep_expertise[]" value="<?= cx_e($stub) ?>" checked>
            <?php if ($display !== ''): ?>
              <?= cx_photo_img($display, 'thumb', ['class' => '', 'alt' => 'Ekspertiz', 'watermark' => false], $siteUrl, $uploadsUrl) ?>
            <?php else: ?>
              <span class="expertise-upload__no-photo">Sayfa</span>
            <?php endif; ?>
            <span class="expertise-upload__keep">Tut</span>
          </label>
        <?php endforeach; ?>
      </div>
    </div>
    <?php endif; ?>

    <label class="expertise-upload__label" for="expertise_photos_input">Rapor fotoğrafları ekle</label>
    <input
      id="expertise_photos_input"
      class="create-input"
      type="file"
      name="expertise_photos[]"
      accept="image/jpeg,image/png,image/webp"
      multiple
    >
    <p class="create-vehicle__hint">En fazla 12 sayfa · JPG/PNG/WEBP</p>
  </details>
</div>
