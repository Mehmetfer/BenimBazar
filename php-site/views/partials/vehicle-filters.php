<?php

declare(strict_types=1);

/** @var string $veh */

/** @var string $q */

/** @var string $region */

/** @var string $kktcCity */

/** @var array<string,mixed> $filters */



$veh = $veh ?? 'otomobil';

$q = $q ?? '';

$region = $region ?? cx_region_from_request(null);

$kktcCity = $kktcCity ?? cx_kktc_city_from_request();

$filters = $filters ?? cx_vehicle_filters_from_request($veh);

$schema = cx_vehicle_filter_schema($veh);

$ranges = cx_vehicle_filter_ranges($veh);

$filtersActive = cx_vehicle_filters_active($filters);

$segmentLabel = cx_vehicle_segment_label($veh);

$clearHref = cx_vehicle_filter_href($veh, $q, []);

$browseStep = cx_vehicle_browse_step($veh, $filters);

$hasWizard = cx_vehicle_browse_has_wizard($veh);

$showDetailFilters = !$hasWizard || $browseStep === 'listings';

?>

<aside class="vehicle-filters" aria-label="Araç filtreleri">

  <div class="vehicle-filters__head">

    <div class="vehicle-filters__head-text">

      <h2 class="vehicle-filters__title">Araç arama</h2>

      <p class="vehicle-filters__subtitle"><?php

        if (cx_vehicle_is_all_mode($veh)) {

            echo 'Marka/model seçmeden km, fiyat ve yıl ile tüm araç ilanlarında arayın.';

        } elseif ($veh === 'ticari' && $browseStep === 'type') {

            echo 'Tür seçimi sağ alanda';

        } elseif ($browseStep === 'brand') {

            if ($veh === 'ticari') {

                echo cx_e(cx_vehicle_commercial_type_short((string) $filters['commercial_type'])) . ' — marka sağ alanda';

            } else {

                echo cx_e($segmentLabel) . ' — marka sağ alanda';

            }

        } elseif ($browseStep === 'model') {

            $mk = is_array($filters['make'] ?? null) && ($filters['make'] ?? []) !== [] ? (string) $filters['make'][0] : '';

            echo cx_e($mk !== '' ? $mk . ' — model sağ alanda' : 'Model seçimi sağ alanda');

        } elseif ($veh === 'ticari' && !empty($filters['commercial_type'])) {

            echo cx_e(cx_vehicle_commercial_type_short((string) $filters['commercial_type'])) . ' — marka, fiyat, yıl…';

        } else {

            echo cx_e($segmentLabel) . ' — marka, fiyat, yıl…';

        }

      ?></p>

    </div>

    <button type="button" class="vehicle-filters__close" data-vehicle-filters-close aria-label="Filtreleri kapat">✕</button>

  </div>

  <a
    class="vehicle-filters__all-vehicles<?= cx_vehicle_is_all_mode($veh) ? ' is-active' : '' ?>"
    href="/index.php?veh=tum-araclar"
  >TÜM ARAÇLAR</a>



  <form class="vehicle-filters__form" method="get" action="/index.php">

    <input type="hidden" name="veh" value="<?= cx_e($veh) ?>">

    <?php foreach (cx_region_query_params() as $rk => $rv): ?>
      <input type="hidden" name="<?= cx_e($rk) ?>" value="<?= cx_e($rv) ?>">
    <?php endforeach; ?>

    <?php if ($q !== ''): ?>

      <input type="hidden" name="q" value="<?= cx_e($q) ?>">

    <?php endif; ?>

    <?php
      $feedSort = cx_listing_sort_from_request();
      if (!cx_listing_sort_is_default($feedSort)):
    ?>
      <input type="hidden" name="sort" value="<?= cx_e($feedSort) ?>">
    <?php endif; ?>



    <?php if ($veh === 'ticari'): ?>

      <?php

        $context = 'sidebar';

        require __DIR__ . '/vehicle-commercial-type-picker.php';

      ?>

    <?php endif; ?>



    <?php if ($showDetailFilters && !cx_vehicle_is_all_mode($veh)): ?>

      <?php if ($veh === 'ticari' && !empty($filters['commercial_type'])): ?>

        <input type="hidden" name="commercial_type" value="<?= cx_e((string) $filters['commercial_type']) ?>">

      <?php endif; ?>

      <?php if (!empty($filters['all_models'])): ?>

        <input type="hidden" name="all_models" value="1">

      <?php endif; ?>

      <?php if (!empty($filters['model'])): ?>

        <input type="hidden" name="model" value="<?= cx_e((string) $filters['model']) ?>">

      <?php endif; ?>

      <?php require __DIR__ . '/vehicle-brand-picker.php'; ?>

    <?php endif; ?>

    <?php if ($showDetailFilters && cx_vehicle_is_all_mode($veh)): ?>
    <div class="vehicle-filter__group vehicle-filter__group--static">
      <label class="vehicle-filter__field">
        <span>Araç türü (isteğe bağlı)</span>
        <select name="arac_seg" class="vehicle-filter__select">
          <option value="">Tümü — otomobil, motosiklet, bisiklet…</option>
          <?php foreach (cx_marketplace_catalog() as $row): ?>
            <option value="<?= cx_e($row['veh']) ?>"<?= (($filters['arac_seg'] ?? '') === $row['veh']) ? ' selected' : '' ?>><?= cx_e($row['label']) ?></option>
          <?php endforeach; ?>
        </select>
      </label>
    </div>
    <?php endif; ?>

    <?php if ($showDetailFilters): ?>

    <div class="vehicle-filters__scroll">

    <?php foreach ($ranges as $range): ?>

    <details class="vehicle-filter__group"<?= !empty($range['open']) ? ' open' : '' ?>>

      <summary class="vehicle-filter__summary"><?= cx_e($range['label']) ?></summary>

      <div class="vehicle-filter__body">

        <div class="vehicle-filter__range">

          <label class="vehicle-filter__field">

            <span>Min<?= !empty($range['suffix']) ? ' (' . cx_e($range['suffix']) . ')' : '' ?></span>

            <input

              type="number"

              name="<?= cx_e($range['min_key']) ?>"

              min="0"

              step="<?= (int) ($range['step'] ?? 1) ?>"

              value="<?= cx_e((string) ($filters[$range['min_key']] ?? '')) ?>"

              placeholder="<?= cx_e($range['min_placeholder'] ?? '0') ?>"

            >

          </label>

          <label class="vehicle-filter__field">

            <span>Max<?= !empty($range['suffix']) ? ' (' . cx_e($range['suffix']) . ')' : '' ?></span>

            <input

              type="number"

              name="<?= cx_e($range['max_key']) ?>"

              min="0"

              step="<?= (int) ($range['step'] ?? 1) ?>"

              value="<?= cx_e((string) ($filters[$range['max_key']] ?? '')) ?>"

              placeholder="<?= cx_e($range['max_placeholder'] ?? '') ?>"

            >

          </label>

        </div>

        <?php if ($range['min_key'] === 'price_min'): ?>

        <label class="vehicle-filter__check">

          <input type="checkbox" name="has_price" value="1"<?= !empty($filters['has_price']) ? ' checked' : '' ?>>

          <span>Sadece fiyatlı ilanlar</span>

        </label>

        <?php endif; ?>

      </div>

    </details>

    <?php endforeach; ?>



    <?php foreach ($schema as $key => $group): ?>

    <details class="vehicle-filter__group">

      <summary class="vehicle-filter__summary"><?= cx_e($group['label']) ?></summary>

      <div class="vehicle-filter__body vehicle-filter__checks">

        <?php foreach ($group['options'] as $opt): ?>

          <?php

            $val = (string) $opt;

            $checked = in_array($val, (array) ($filters[$key] ?? []), true)

                || in_array((int) $opt, (array) ($filters[$key] ?? []), true);

          ?>

          <label class="vehicle-filter__check">

            <input type="checkbox" name="<?= cx_e($key) ?>[]" value="<?= cx_e($val) ?>"<?= $checked ? ' checked' : '' ?>>

            <span><?= cx_e($val) ?></span>

          </label>

        <?php endforeach; ?>

      </div>

    </details>

    <?php endforeach; ?>



    <details class="vehicle-filter__group">

      <summary class="vehicle-filter__summary">Medya</summary>

      <div class="vehicle-filter__body vehicle-filter__checks">

        <label class="vehicle-filter__check">

          <input type="checkbox" name="has_photos" value="1"<?= !empty($filters['has_photos']) ? ' checked' : '' ?>>

          <span>Fotoğraflı ilanlar</span>

        </label>

      </div>

    </details>



    <div class="vehicle-filters__actions">

      <button type="submit" class="vehicle-filters__apply">Filtrele</button>

      <?php if ($filtersActive): ?>

        <a class="vehicle-filters__reset" href="<?= cx_e($clearHref) ?>">Temizle</a>

      <?php endif; ?>

    </div>

    </div>

    <?php endif; ?>

  </form>

</aside>

