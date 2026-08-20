<?php

declare(strict_types=1);

/** @var string $prefillSegment */
/** @var bool $vehicleFormRelaxed */
/** @var array<string, string|int> $prefillForm */

$prefillSegment = $prefillSegment ?? '';
$vehicleFormRelaxed = $vehicleFormRelaxed ?? false;
$prefillForm = $prefillForm ?? [];
$vehRequired = $vehicleFormRelaxed ? '' : ' data-vehicle-required="1"';
$makeRequired = ' data-vehicle-required="1"';

$prefillMake = trim((string) ($prefillForm['vehicle_make'] ?? ''));
$prefillModel = trim((string) ($prefillForm['vehicle_model'] ?? ''));
$customModelOpt = cx_vehicle_model_custom_option();
$modelInCatalog = $prefillSegment !== '' && $prefillMake !== ''
    && $prefillModel !== ''
    && cx_vehicle_model_in_catalog($prefillModel, $prefillSegment, $prefillMake);
$useCustomModel = $prefillModel !== '' && !$modelInCatalog && $prefillMake !== '' && $prefillMake !== 'Diğer';
$prefillModelCustom = $useCustomModel
    ? $prefillModel
    : trim((string) ($prefillForm['vehicle_model_custom'] ?? ''));
$prefillModelSelect = $useCustomModel ? $customModelOpt : $prefillModel;
$brandRows = $prefillSegment !== '' ? cx_vehicle_brand_catalog($prefillSegment) : [];
$modelRows = ($prefillSegment !== '' && $prefillMake !== '')
    ? cx_vehicle_model_catalog($prefillSegment, $prefillMake)
    : [];
if ($prefillMake === 'Diğer' && $modelRows === []) {
    $modelRows = ['Diğer'];
}

$motoSchema = cx_motorcycle_filter_schema();
$carSchema = cx_vehicle_filter_schema('otomobil');
$bikeSchema = cx_bicycle_filter_schema();
$antikaSchema = cx_antique_vehicle_filter_schema();
$ticariSchema = $carSchema;
unset($ticariSchema['doors']);
$brandModelMap = cx_vehicle_make_model_form_map();

$showSteering = !empty($showSteeringField) || cx_user_is_kktc($user ?? cx_current_user());
$prefillSteering = trim((string) ($prefillForm['vehicle_steering'] ?? ''));
$steerRight = $prefillSteering === 'right' || str_contains(mb_strtolower($prefillSteering, 'UTF-8'), 'sağ') || str_contains(mb_strtolower($prefillSteering, 'UTF-8'), 'sag');
$steerLeft = $prefillSteering === 'left' || str_contains(mb_strtolower($prefillSteering, 'UTF-8'), 'sol');
$prefillFuel = trim((string) ($prefillForm['vehicle_fuel'] ?? ''));
$prefillTrans = trim((string) ($prefillForm['vehicle_transmission'] ?? ''));
$prefillCommercial = trim((string) ($prefillForm['vehicle_commercial_type'] ?? ''));
?>

<input type="hidden" name="vehicle_segment" id="vehicle_segment" value="<?= cx_e($prefillSegment) ?>">

<fieldset class="create-vehicle" id="vehicle_fields" data-vehicle-relaxed="<?= $vehicleFormRelaxed ? '1' : '0' ?>" data-vehicle-steps="1">
  <legend class="create-vehicle__legend">Araç bilgileri</legend>
  <p class="create-vehicle__hint" data-veh-steps-hint>
    <?= $vehicleFormRelaxed
      ? 'Admin: yalnızca marka zorunlu.'
      : 'Önce marka, model, yıl ve km girin — sonraki alanlar otomatik açılır.' ?>
  </p>

  <div id="vehicle_detail_fields" class="create-vehicle__steps"<?= $prefillSegment === '' ? ' hidden' : '' ?>>

    <div class="create-vehicle__step is-open" data-veh-step="1">
      <h3 class="create-vehicle__step-title">1 · Temel</h3>
      <div class="create-vehicle__grid">

        <label class="create-vehicle__field" data-veh-segment="ticari" hidden>
          <span>Ticari araç türü *</span>
          <select name="vehicle_commercial_type" class="create-input"<?= $vehRequired ?> id="vehicle_commercial_type" data-step-field="1">
            <option value="">Tür seçin</option>
            <?php foreach (cx_vehicle_commercial_types() as $id => $row): ?>
              <option value="<?= cx_e($id) ?>"<?= $prefillCommercial === (string) $id || $prefillCommercial === (string) ($row['label'] ?? '') ? ' selected' : '' ?>><?= cx_e($row['label']) ?></option>
            <?php endforeach; ?>
          </select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="motosiklet otomobil antika-arac ticari bisiklet" hidden>
          <span>Marka *</span>
          <select name="vehicle_make" id="vehicle_make_select" class="create-input"<?= $makeRequired ?> data-step-field="1">
            <option value="">Marka seçin</option>
            <?php foreach ($brandRows as $brand): ?>
              <option value="<?= cx_e($brand['name']) ?>"<?= $prefillMake === $brand['name'] ? ' selected' : '' ?>><?= cx_e($brand['name']) ?></option>
            <?php endforeach; ?>
          </select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="motosiklet otomobil antika-arac ticari bisiklet" hidden>
          <span>Model *</span>
          <select name="vehicle_model" id="vehicle_model_select" class="create-input"<?= $vehRequired ?><?= $prefillMake === '' ? ' disabled' : '' ?> data-step-field="1">
            <option value=""><?= $prefillMake === '' ? 'Önce marka seçin' : 'Model seçin' ?></option>
            <?php foreach ($modelRows as $modelName): ?>
              <option value="<?= cx_e($modelName) ?>"<?= $prefillModelSelect === $modelName ? ' selected' : '' ?>><?= cx_e($modelName) ?></option>
            <?php endforeach; ?>
            <?php if ($prefillMake !== '' && $prefillMake !== 'Diğer'): ?>
              <option value="<?= cx_e($customModelOpt) ?>"<?= $prefillModelSelect === $customModelOpt ? ' selected' : '' ?>>Listede yok — elle yaz</option>
            <?php endif; ?>
          </select>
          <input
            type="text"
            name="vehicle_model_custom"
            id="vehicle_model_custom"
            class="create-input create-vehicle__model-custom"
            maxlength="48"
            placeholder="Örnek: Celica, E36, R1..."
            value="<?= cx_e($prefillModelCustom) ?>"
            data-step-field="1"
            <?= ($prefillModelSelect !== $customModelOpt && !$useCustomModel) ? 'hidden' : '' ?>
          >
        </label>

        <label class="create-vehicle__field" data-veh-segment="all" hidden>
          <span data-veh-year-label="1">Model yılı *</span>
          <input class="create-input" type="number" name="vehicle_year" min="1980" max="2099"<?= $vehRequired ?> data-step-field="1" value="<?= cx_e((string) ($prefillForm['vehicle_year'] ?? '')) ?>">
        </label>

        <label class="create-vehicle__field" data-veh-segment="all" data-veh-km-wrap="1" hidden>
          <span data-veh-km-label="1">Kilometre *</span>
          <input class="create-input" type="number" name="vehicle_km" min="0"<?= $vehRequired ?> data-veh-km="1" data-step-field="1" value="<?= cx_e((string) ($prefillForm['vehicle_km'] ?? '')) ?>">
        </label>

      </div>
      <p class="create-vehicle__step-note" data-step-gate="2">Marka, model, yıl ve km girilince teknik alanlar açılır.</p>
    </div>

    <div class="create-vehicle__step" data-veh-step="2" hidden>
      <h3 class="create-vehicle__step-title">2 · Teknik</h3>
      <div class="create-vehicle__grid">

        <label class="create-vehicle__field" data-veh-segment="otomobil motosiklet ticari antika-arac" hidden>
          <span>Yakıt tipi *</span>
          <select name="vehicle_fuel" class="create-input"<?= $vehRequired ?> data-veh-options="fuel" data-step-field="2">
            <option value="">Seçin</option>
            <?php foreach (['Benzin', 'Dizel', 'Hibrit', 'Elektrik', 'LPG'] as $fuelOpt): ?>
              <option value="<?= cx_e($fuelOpt) ?>"<?= $prefillFuel === $fuelOpt ? ' selected' : '' ?>><?= cx_e($fuelOpt) ?></option>
            <?php endforeach; ?>
          </select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="otomobil motosiklet ticari antika-arac" hidden>
          <span data-veh-trans-label="1">Vites *</span>
          <select name="vehicle_transmission" class="create-input"<?= $vehRequired ?> data-veh-options="transmission" data-step-field="2">
            <option value="">Seçin</option>
            <?php foreach (['Manuel', 'Otomatik', 'Yarı otomatik'] as $transOpt): ?>
              <option value="<?= cx_e($transOpt) ?>"<?= $prefillTrans === $transOpt ? ' selected' : '' ?>><?= cx_e($transOpt) ?></option>
            <?php endforeach; ?>
          </select>
        </label>

        <?php if ($showSteering): ?>
        <label class="create-vehicle__field create-vehicle__field--steering" data-veh-segment="otomobil motosiklet ticari antika-arac" hidden>
          <span>Dümen *</span>
          <select name="vehicle_steering" class="create-input"<?= $vehicleFormRelaxed ? '' : ' required' ?> data-vehicle-required="1" data-step-field="2">
            <option value="">Seçin</option>
            <option value="right"<?= $steerRight ? ' selected' : '' ?>>Sağ dümen</option>
            <option value="left"<?= $steerLeft ? ' selected' : '' ?>>Sol dümen</option>
          </select>
        </label>
        <?php endif; ?>

        <label class="create-vehicle__field" data-veh-segment="otomobil motosiklet ticari antika-arac" hidden>
          <span>Motor hacmi (cc)<span data-veh-cc-req hidden> *</span></span>
          <input class="create-input" type="number" name="vehicle_engine_cc" min="0" data-veh-cc="1" data-step-field="2" value="<?= cx_e((string) ($prefillForm['vehicle_engine_cc'] ?? '')) ?>">
        </label>

        <label class="create-vehicle__field" data-veh-segment="otomobil motosiklet ticari antika-arac" hidden>
          <span>Beygir (HP)</span>
          <input class="create-input" type="number" name="vehicle_hp" min="0" data-step-field="2" value="<?= cx_e((string) ($prefillForm['vehicle_hp'] ?? '')) ?>">
        </label>

        <label class="create-vehicle__field" data-veh-segment="motosiklet" hidden>
          <span>Motosiklet tipi</span>
          <select name="vehicle_moto_type" class="create-input" data-veh-options="moto_type" data-step-field="2"></select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="bisiklet" hidden>
          <span>Bisiklet tipi</span>
          <select name="vehicle_bike_type" class="create-input" data-veh-options="bike_type" data-step-field="2"></select>
        </label>

      </div>
      <p class="create-vehicle__step-note" data-step-gate="3">Yakıt ve vites (veya bisiklet tipi) seçilince ek alanlar açılır.</p>
    </div>

    <div class="create-vehicle__step" data-veh-step="3" hidden>
      <h3 class="create-vehicle__step-title">3 · Detay (opsiyonel)</h3>
      <div class="create-vehicle__grid">

        <label class="create-vehicle__field" data-veh-segment="motosiklet" hidden>
          <span>Zamanlama</span>
          <select name="vehicle_stroke" class="create-input" data-veh-options="stroke"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="motosiklet" hidden>
          <span>Silindir sayısı</span>
          <select name="vehicle_cylinders" class="create-input" data-veh-options="cylinders"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="motosiklet" hidden>
          <span>Aktarma</span>
          <select name="vehicle_drive_train" class="create-input" data-veh-options="drive_train"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="motosiklet" hidden>
          <span>Emisyon sınıfı</span>
          <select name="vehicle_emission" class="create-input" data-veh-options="emission"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="motosiklet" hidden>
          <span>Hasar durumu</span>
          <select name="vehicle_damage" class="create-input" data-veh-options="damage"></select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="bisiklet" hidden>
          <span>Kadro malzemesi</span>
          <select name="vehicle_frame" class="create-input" data-veh-options="frame"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="bisiklet" hidden>
          <span>Jant boyutu</span>
          <select name="vehicle_wheel" class="create-input" data-veh-options="wheel"></select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="otomobil ticari antika-arac" hidden>
          <span>Çekiş</span>
          <select name="vehicle_drive" class="create-input" data-veh-options="drive"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="otomobil ticari antika-arac" hidden>
          <span>Kasa tipi</span>
          <select name="vehicle_body" class="create-input" data-veh-options="body"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="otomobil ticari antika-arac" hidden>
          <span>Kapı sayısı</span>
          <select name="vehicle_doors" class="create-input" data-veh-options="doors"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="antika-arac" hidden>
          <span>Dönem</span>
          <select name="vehicle_era" class="create-input" data-veh-options="era"></select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="all" hidden>
          <span>Renk</span>
          <select name="vehicle_color" class="create-input" data-veh-options="color"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="motosiklet bisiklet antika-arac otomobil ticari" hidden>
          <span data-veh-condition-label="1">Durum</span>
          <select name="vehicle_condition" class="create-input" data-veh-options="condition"></select>
        </label>

        <label class="create-vehicle__field" data-veh-segment="all" hidden>
          <span>Satıcı tipi</span>
          <select name="seller_type" class="create-input" data-veh-options="seller_type"></select>
        </label>
        <label class="create-vehicle__field" data-veh-segment="all" hidden>
          <span>Telefon</span>
          <input class="create-input" type="tel" name="seller_phone" placeholder="+90 5xx xxx xx xx" value="<?= cx_e((string) ($prefillForm['seller_phone'] ?? '')) ?>">
        </label>
        <label class="create-vehicle__field create-vehicle__field--wide" data-veh-segment="all" hidden>
          <span>Web sitesi</span>
          <input class="create-input" type="url" name="seller_website" placeholder="https://" value="<?= cx_e((string) ($prefillForm['seller_website'] ?? '')) ?>">
        </label>
        <label class="create-vehicle__field create-vehicle__field--wide" data-veh-segment="all" hidden>
          <span>Donanım / özellikler</span>
          <textarea class="create-input create-input--area" name="vehicle_equipment" rows="3" placeholder="ABS, alarm, deri koltuk…"><?= cx_e((string) ($prefillForm['vehicle_equipment'] ?? '')) ?></textarea>
        </label>

      </div>
    </div>

  </div>
</fieldset>

<script>
window.cxVehicleFormOptions = {
  otomobil: <?= json_encode($carSchema, JSON_UNESCAPED_UNICODE) ?>,
  motosiklet: <?= json_encode($motoSchema, JSON_UNESCAPED_UNICODE) ?>,
  bisiklet: <?= json_encode($bikeSchema, JSON_UNESCAPED_UNICODE) ?>,
  ticari: <?= json_encode($ticariSchema, JSON_UNESCAPED_UNICODE) ?>,
  'antika-arac': <?= json_encode($antikaSchema, JSON_UNESCAPED_UNICODE) ?>
};
window.cxVehicleBrandModels = <?= json_encode($brandModelMap, JSON_UNESCAPED_UNICODE) ?>;
window.cxVehicleModelCustomOption = <?= json_encode($customModelOpt, JSON_UNESCAPED_UNICODE) ?>;
</script>
