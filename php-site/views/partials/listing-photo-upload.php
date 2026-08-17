<?php

declare(strict_types=1);

/** @var string $uploadInputId */
/** @var string $uploadLabel */

$uploadInputId = $uploadInputId ?? 'listing_photos_upload';
$uploadLabel = $uploadLabel ?? 'Fotograflar';

?>
<div class="listing-photo-upload" data-photo-upload>
  <label for="<?= cx_e($uploadInputId) ?>"><?= cx_e($uploadLabel) ?></label>
  <input
    id="<?= cx_e($uploadInputId) ?>"
    type="file"
    name="photos[]"
    accept="image/jpeg,image/png,image/webp"
    multiple
    data-photo-file-input
  >
  <p class="listing-photo-editor__hint">Yukledikten sonra <strong>Ana foto</strong> ile kapak gorselini secin. Secmezseniz ilk foto ana ekranda gorunur.</p>
  <div class="listing-photo-editor__grid" data-photo-upload-grid hidden></div>
  <input type="hidden" name="cover_photo_new" value="" data-cover-photo-new>
</div>
