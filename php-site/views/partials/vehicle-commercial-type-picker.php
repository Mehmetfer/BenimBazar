<?php
declare(strict_types=1);
/** @var string $veh */
/** @var string $q */
/** @var array<string,mixed> $filters */
/** @var string $context sidebar|main */

$veh = $veh ?? 'ticari';
$q = $q ?? '';
$filters = $filters ?? cx_vehicle_filters_from_request($veh);
$context = $context ?? 'sidebar';
$types = cx_vehicle_commercial_types();
$counts = cx_vehicle_commercial_type_counts();
$selected = trim((string) ($filters['commercial_type'] ?? ''));
?>
<?php if ($selected !== '' && cx_vehicle_commercial_type_valid($selected)): ?>
  <div class="vehicle-commercial-type__chosen vehicle-commercial-type__chosen--<?= cx_e($context) ?>">
    <span class="vehicle-commercial-type__chosen-label">Seçili tür</span>
    <strong><?= cx_e(cx_vehicle_commercial_type_label($selected)) ?></strong>
    <a class="vehicle-commercial-type__change" href="<?= cx_e(cx_vehicle_filter_href('ticari', $q, [])) ?>">Tür değiştir</a>
  </div>
<?php elseif ($context === 'main'): ?>
  <div class="vehicle-commercial-type vehicle-commercial-type--main">
    <p class="vehicle-commercial-type__step">1 / 3 — Ticari tür</p>
    <p class="vehicle-commercial-type__title">Ticari araç türü seçin</p>
    <p class="vehicle-commercial-type__hint">Tür → marka → model adımlarıyla arama yapın.</p>
    <div class="vehicle-commercial-type__grid" role="list">
      <?php foreach ($types as $id => $row): ?>
        <?php $count = (int) ($counts[$id] ?? 0); ?>
        <a
          class="vehicle-commercial-type__card<?= $count === 0 ? ' is-empty' : '' ?>"
          role="listitem"
          href="<?= cx_e(cx_vehicle_commercial_type_href($id, $q, $filters)) ?>"
          title="<?= cx_e($row['label']) ?>"
        >
          <?= cx_vehicle_commercial_type_icon_svg((string) $row['icon']) ?>
          <span class="vehicle-commercial-type__name"><?= cx_e($row['short']) ?></span>
          <?php if ($count > 0): ?>
            <span class="vehicle-commercial-type__count">(<?= cx_e(number_format($count, 0, ',', '.')) ?>)</span>
          <?php endif; ?>
        </a>
      <?php endforeach; ?>
    </div>
  </div>
<?php endif; ?>
