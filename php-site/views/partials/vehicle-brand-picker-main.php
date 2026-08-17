<?php
declare(strict_types=1);
/** @var string $veh */
/** @var string $q */
/** @var array<string,mixed> $filters */

$veh = $veh ?? 'ticari';
$q = $q ?? '';
$filters = $filters ?? cx_vehicle_filters_from_request($veh);
$picker = cx_vehicle_brand_picker_data($veh, $filters);
$isTicari = $veh === 'ticari';
$typeId = (string) ($filters['commercial_type'] ?? '');
$typeShort = $isTicari ? cx_vehicle_commercial_type_short($typeId) : '';
$stepLabel = $isTicari ? '2 / 3 — Marka' : '1 / 2 — Marka';
$title = $isTicari
    ? $typeShort . ' — marka seçin'
    : cx_vehicle_segment_label($veh) . ' — marka seçin';
$hint = 'Markaya tıklayınca o markanın modelleri listelenir.';
$backHref = $isTicari
    ? cx_vehicle_filter_href('ticari', $q, [])
    : cx_vehicle_filter_href($veh, $q, []);
$backText = $isTicari ? '← Tür değiştir' : '← Kategoriye dön';
?>
<div class="vehicle-brand-main" data-brand-main>
  <div class="vehicle-brand-main__head">
    <div>
      <p class="vehicle-brand-main__step"><?= cx_e($stepLabel) ?></p>
      <h3 class="vehicle-brand-main__title"><?= cx_e($title) ?></h3>
      <p class="vehicle-brand-main__hint"><?= cx_e($hint) ?></p>
    </div>
    <a class="vehicle-brand-main__back" href="<?= cx_e($backHref) ?>"><?= cx_e($backText) ?></a>
  </div>

  <div class="vehicle-brand-main__search-wrap">
    <input
      type="search"
      class="vehicle-brand-main__search"
      data-brand-main-search
      placeholder="Hangi markayı arıyorsunuz?"
      autocomplete="off"
    >
  </div>

  <?php if ($picker['popular'] !== []): ?>
  <div class="vehicle-brand-main__section">
    <p class="vehicle-brand-main__section-title">Popüler markalar</p>
    <div class="vehicle-brand-main__grid">
      <?php foreach ($picker['popular'] as $brand): ?>
        <?php
          $initial = mb_strtoupper(mb_substr($brand['name'], 0, 1, 'UTF-8'), 'UTF-8');
          $href = cx_vehicle_filter_href($veh, $q, array_merge($filters, ['make' => [$brand['name']]]));
          $count = (int) $brand['count'];
        ?>
        <a
          class="vehicle-brand-main__logo-card<?= $count === 0 ? ' is-empty' : '' ?>"
          href="<?= cx_e($href) ?>"
          data-brand-main-item
          data-brand-name="<?= cx_e(mb_strtolower($brand['name'], 'UTF-8')) ?>"
          title="<?= cx_e($brand['name']) ?>"
        >
          <span class="vehicle-brand-main__logo-box">
            <?php if ($brand['logo'] !== ''): ?>
            <img
              <?= cx_vehicle_brand_logo_attrs($brand) ?>
              alt=""
              loading="lazy"
            >
            <?php endif; ?>
            <span class="vehicle-brand-picker__logo-fallback"<?= $brand['logo'] !== '' ? ' style="display:none"' : '' ?>><?= cx_e($initial) ?></span>
          </span>
          <span class="vehicle-brand-main__logo-name"><?= cx_e($brand['name']) ?></span>
          <?php if ($count > 0): ?>
            <span class="vehicle-brand-main__logo-count">(<?= cx_e(number_format($count, 0, ',', '.')) ?>)</span>
          <?php endif; ?>
        </a>
      <?php endforeach; ?>
    </div>
  </div>
  <?php endif; ?>

  <div class="vehicle-brand-main__section">
    <p class="vehicle-brand-main__section-title">Tüm markalar</p>
    <ul class="vehicle-brand-main__list">
      <?php foreach ($picker['all'] as $brand): ?>
        <?php
          $initial = mb_strtoupper(mb_substr($brand['name'], 0, 1, 'UTF-8'), 'UTF-8');
          $href = cx_vehicle_filter_href($veh, $q, array_merge($filters, ['make' => [$brand['name']]]));
          $count = (int) $brand['count'];
        ?>
        <li
          class="vehicle-brand-main__item<?= $count === 0 ? ' is-empty' : '' ?>"
          data-brand-main-item
          data-brand-name="<?= cx_e(mb_strtolower($brand['name'], 'UTF-8')) ?>"
        >
          <a class="vehicle-brand-main__row" href="<?= cx_e($href) ?>">
            <span class="vehicle-brand-picker__row-logo">
              <?php if ($brand['logo'] !== ''): ?>
              <img
                <?= cx_vehicle_brand_logo_attrs($brand) ?>
                alt=""
                loading="lazy"
              >
              <?php endif; ?>
              <span class="vehicle-brand-picker__logo-fallback"<?= $brand['logo'] !== '' ? ' style="display:none"' : '' ?>><?= cx_e($initial) ?></span>
            </span>
            <span class="vehicle-brand-main__row-name">
              <?= cx_e($brand['name']) ?>
              <span class="vehicle-brand-main__row-count">(<?= cx_e(number_format($count, 0, ',', '.')) ?>)</span>
            </span>
            <span class="vehicle-brand-main__row-arrow" aria-hidden="true">›</span>
          </a>
        </li>
      <?php endforeach; ?>
    </ul>
  </div>
</div>
