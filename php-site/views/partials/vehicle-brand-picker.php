<?php
declare(strict_types=1);
/** @var string $veh */
/** @var array<string,mixed> $filters */

$veh = $veh ?? 'otomobil';
$filters = $filters ?? cx_vehicle_filters_from_request($veh);
$picker = cx_vehicle_brand_picker_data($veh, $filters);
$selected = $picker['selected'];
$summary = cx_vehicle_brand_picker_summary($selected);
$modelVal = (string) ($filters['model'] ?? '');
$modelDisabled = $selected === [];
?>
<div class="vehicle-brand-row">
  <div class="vehicle-brand-picker" data-brand-picker>
    <label class="vehicle-brand-picker__label" id="vehicle-brand-label">Marka</label>
    <div class="vehicle-brand-picker__control">
      <button
        type="button"
        class="vehicle-brand-picker__trigger<?= $selected !== [] ? ' is-filled' : '' ?>"
        data-brand-trigger
        aria-expanded="false"
        aria-labelledby="vehicle-brand-label"
      >
        <span class="vehicle-brand-picker__trigger-text" data-brand-summary><?= cx_e($summary) ?></span>
        <span class="vehicle-brand-picker__caret" aria-hidden="true"></span>
      </button>
      <div class="vehicle-brand-picker__panel" data-brand-panel hidden>
        <div class="vehicle-brand-picker__search-wrap">
          <input
            type="search"
            class="vehicle-brand-picker__search"
            data-brand-search
            placeholder="Hangi markayı arıyorsunuz?"
            autocomplete="off"
          >
        </div>
        <?php if ($picker['popular'] !== []): ?>
        <div class="vehicle-brand-picker__section">
          <p class="vehicle-brand-picker__section-title">Popüler markalar</p>
          <div class="vehicle-brand-picker__grid">
            <?php foreach ($picker['popular'] as $brand): ?>
              <?php
                $isOn = in_array($brand['name'], $selected, true);
                $initial = mb_strtoupper(mb_substr($brand['name'], 0, 1, 'UTF-8'), 'UTF-8');
              ?>
              <button
                type="button"
                class="vehicle-brand-picker__logo-btn<?= $isOn ? ' is-selected' : '' ?>"
                data-brand-logo-toggle
                data-brand-name="<?= cx_e($brand['name']) ?>"
                title="<?= cx_e($brand['name']) ?>"
              >
                <span class="vehicle-brand-picker__logo-box">
                  <?php if ($brand['logo'] !== ''): ?>
                  <img
                    <?= cx_vehicle_brand_logo_attrs($brand) ?>
                    alt=""
                    loading="lazy"
                  >
                  <?php endif; ?>
                  <span class="vehicle-brand-picker__logo-fallback"<?= $brand['logo'] !== '' ? ' style="display:none"' : '' ?>><?= cx_e($initial) ?></span>
                </span>
              </button>
            <?php endforeach; ?>
          </div>
        </div>
        <?php endif; ?>
        <div class="vehicle-brand-picker__section vehicle-brand-picker__section--list">
          <p class="vehicle-brand-picker__section-title">Tüm markalar</p>
          <ul class="vehicle-brand-picker__list" data-brand-list>
            <?php foreach ($picker['all'] as $brand): ?>
              <?php
                $isOn = in_array($brand['name'], $selected, true);
                $initial = mb_strtoupper(mb_substr($brand['name'], 0, 1, 'UTF-8'), 'UTF-8');
                $count = (int) $brand['count'];
              ?>
              <li
                class="vehicle-brand-picker__item<?= $count === 0 ? ' is-empty' : '' ?>"
                data-brand-item
                data-brand-name="<?= cx_e(mb_strtolower($brand['name'], 'UTF-8')) ?>"
              >
                <label class="vehicle-brand-picker__row">
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
                  <span class="vehicle-brand-picker__row-name">
                    <?= cx_e($brand['name']) ?>
                    <span class="vehicle-brand-picker__count">(<?= cx_e(number_format($count, 0, ',', '.')) ?>)</span>
                  </span>
                  <input
                    type="checkbox"
                    class="vehicle-brand-picker__checkbox"
                    name="make[]"
                    value="<?= cx_e($brand['name']) ?>"
                    data-brand-checkbox
                    <?= $isOn ? ' checked' : '' ?>
                    <?= $count === 0 ? ' disabled' : '' ?>
                  >
                </label>
              </li>
            <?php endforeach; ?>
          </ul>
        </div>
      </div>
    </div>
  </div>

  <div class="vehicle-brand-model">
    <label class="vehicle-brand-picker__label" for="vehicle-filter-model">Model</label>
    <input
      type="text"
      id="vehicle-filter-model"
      class="vehicle-brand-model__input<?= $modelDisabled ? ' is-disabled' : '' ?>"
      name="model"
      value="<?= cx_e($modelVal) ?>"
      placeholder="Model seçin"
      <?= $modelDisabled ? ' disabled' : '' ?>
      data-brand-model
    >
  </div>
</div>
