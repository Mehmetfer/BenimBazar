<?php

declare(strict_types=1);

/** @var string $veh */

/** @var string $q */

/** @var array<string,mixed> $filters */



$veh = $veh ?? 'ticari';

$q = $q ?? '';

$filters = $filters ?? cx_vehicle_filters_from_request($veh);

$picker = cx_vehicle_model_picker_data($veh, $filters);

$make = $picker['make'];

$isTicari = $veh === 'ticari';

$typeId = (string) ($filters['commercial_type'] ?? '');

$typeShort = $isTicari ? cx_vehicle_commercial_type_short($typeId) : '';

$stepLabel = $isTicari ? '3 / 3 — Model' : '2 / 2 — Model';

$brandBackHref = $isTicari

    ? cx_vehicle_filter_href('ticari', $q, ['commercial_type' => $typeId])

    : cx_vehicle_filter_href($veh, $q, []);

$allModelsHref = cx_vehicle_filter_href($veh, $q, array_merge($filters, ['all_models' => true, 'model' => null]));

$brandRow = ['name' => $make, 'domain' => ''];

foreach (cx_vehicle_brand_catalog($veh) as $b) {

    if ($b['name'] === $make) {

        $brandRow = $b;

        break;

    }

}

$logoPaths = cx_vehicle_brand_logo_paths($make, (string) ($brandRow['domain'] ?? ''));

$brandRow['logo'] = $logoPaths[0] ?? '';

$brandRow['logo_fallbacks'] = array_slice($logoPaths, 1);

$hint = $isTicari

    ? $typeShort . ' · model seçin veya tüm ilanları görün'

    : 'Model seçin veya tüm ' . $make . ' ilanlarını görün';

?>

<div class="vehicle-model-main" data-model-main>

  <div class="vehicle-model-main__head">

    <div class="vehicle-model-main__brand">

      <?php if ($brandRow['logo'] !== ''): ?>

      <span class="vehicle-model-main__brand-logo">

        <img <?= cx_vehicle_brand_logo_attrs($brandRow) ?> alt="">

      </span>

      <?php endif; ?>

      <div>

        <p class="vehicle-model-main__step"><?= cx_e($stepLabel) ?></p>

        <h3 class="vehicle-model-main__title"><?= cx_e($make) ?></h3>

        <p class="vehicle-model-main__hint"><?= cx_e($hint) ?></p>

      </div>

    </div>

    <a class="vehicle-model-main__back" href="<?= cx_e($brandBackHref) ?>">← Marka değiştir</a>

  </div>



  <div class="vehicle-model-main__search-wrap">

    <input

      type="search"

      class="vehicle-model-main__search"

      data-model-main-search

      placeholder="Hangi modeli arıyorsunuz?"

      autocomplete="off"

    >

  </div>



  <?php if ($picker['total'] > 0): ?>

  <a class="vehicle-model-main__all" href="<?= cx_e($allModelsHref) ?>">

    Tüm <?= cx_e($make) ?> ilanları (<?= cx_e(number_format($picker['total'], 0, ',', '.')) ?>)

  </a>

  <?php endif; ?>



  <ul class="vehicle-model-main__list">

    <?php foreach ($picker['models'] as $row): ?>

      <?php

        $href = cx_vehicle_filter_href($veh, $q, array_merge($filters, ['model' => $row['name'], 'all_models' => null]));

        $count = (int) $row['count'];

      ?>

      <li

        class="vehicle-model-main__item<?= $count === 0 ? ' is-empty' : '' ?>"

        data-model-main-item

        data-model-name="<?= cx_e(mb_strtolower($row['name'], 'UTF-8')) ?>"

      >

        <a class="vehicle-model-main__row" href="<?= cx_e($href) ?>">

          <span class="vehicle-model-main__name"><?= cx_e($row['name']) ?></span>

          <span class="vehicle-model-main__count">(<?= cx_e(number_format($count, 0, ',', '.')) ?>)</span>

          <span class="vehicle-model-main__arrow" aria-hidden="true">›</span>

        </a>

      </li>

    <?php endforeach; ?>

  </ul>

</div>

