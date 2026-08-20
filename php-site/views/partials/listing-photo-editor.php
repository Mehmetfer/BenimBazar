<?php

declare(strict_types=1);

/** @var list<string> $photoStubs */
/** @var string $coverStub */

$photoStubs = $photoStubs ?? [];
$coverStub = trim((string) ($coverStub ?? ($photoStubs[0] ?? '')));
$appCfg = cx_app_config();
$uploadsUrl = (string) ($appCfg['uploads_url'] ?? '/uploads');
$siteUrl = (string) ($appCfg['url'] ?? '');

?>
<div class="listing-photo-editor" data-photo-editor>
  <input type="hidden" name="photo_editor" value="1">
  <p class="listing-photo-editor__hint">
    <strong>Ana foto:</strong> kapak gorseli secin (isaretlemezseniz ilk foto kullanilir).
    Kaldirmak icin &times; tusuna basin.
  </p>
  <?php if ($photoStubs === []): ?>
    <p class="listing-photo-editor__empty">Henuz fotograf yok.</p>
  <?php else: ?>
    <div class="listing-photo-editor__grid">
      <?php foreach ($photoStubs as $i => $stub):
        $display = cx_photo_urls([$stub], $uploadsUrl)[0] ?? '';
        $isCover = ($coverStub !== '' && $stub === $coverStub) || ($coverStub === '' && $i === 0);
      ?>
      <div class="listing-photo-editor__item<?= $isCover ? ' listing-photo-editor__item--cover' : '' ?>" data-photo-item data-photo-stub="<?= cx_e($stub) ?>">
        <input type="hidden" name="keep_photos[]" value="<?= cx_e($stub) ?>">
        <label class="listing-photo-editor__cover-btn">
          <input
            type="radio"
            name="cover_photo"
            value="<?= cx_e($stub) ?>"
            class="listing-photo-editor__cover-input"
            data-photo-cover-existing
            <?= $isCover ? ' checked' : '' ?>
          >
          <span>Ana foto</span>
        </label>
        <div class="listing-photo-editor__thumb">
          <?= cx_photo_img($display, 'thumb', ['alt' => 'Ilan fotografi', 'loading' => 'lazy', 'watermark' => false], $siteUrl, $uploadsUrl) ?>
        </div>
        <button type="button" class="listing-photo-editor__remove" data-photo-remove aria-label="Fotografi kaldir">&times;</button>
      </div>
      <?php endforeach; ?>
    </div>
  <?php endif; ?>
</div>
