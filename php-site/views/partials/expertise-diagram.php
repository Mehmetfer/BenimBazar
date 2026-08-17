<?php

declare(strict_types=1);

/** @var bool $expertiseReadonly */
/** @var array<string,string> $expertiseParts */

$expertiseReadonly = !empty($expertiseReadonly);
$expertiseParts = is_array($expertiseParts ?? null) ? $expertiseParts : [];
$partLabels = cx_expertise_body_parts();
$statuses = cx_expertise_part_statuses();
$statusAbbrevs = cx_expertise_status_abbrevs();
$statusColors = [
    'Orijinal' => '#2ecc71',
    'Boyalı' => '#8e44ad',
    'Lokal boyalı' => '#5dade2',
    'Plastik' => '#4a4a4a',
    'Değişmiş' => '#e74c3c',
    'Sökme/takma' => '#2980b9',
    'Vernik' => '#922b21',
    'Ezik' => '#e67e22',
];
?>
<div
  class="expertise-diagram<?= $expertiseReadonly ? ' expertise-diagram--readonly' : '' ?>"
  data-expertise-diagram
  data-expertise-readonly="<?= $expertiseReadonly ? '1' : '0' ?>"
>
  <div class="expertise-diagram__head">
    <strong>Kaporta / boya durumu</strong>
    <?php if (!$expertiseReadonly): ?>
      <span>Parçaya tıklayın, durumu seçin</span>
    <?php endif; ?>
  </div>

  <div class="expertise-diagram__canvas">
    <svg class="expertise-diagram__svg" viewBox="0 0 1024 682" role="img" aria-label="Araç kaporta şeması — beş görünüş">
      <image href="/assets/expertise/vehicle-views.png" xlink:href="/assets/expertise/vehicle-views.png" x="0" y="0" width="1024" height="682" preserveAspectRatio="xMidYMid meet"></image>

      <!-- SOL YAN (üst): burun sola — kutu ~210,16–864,214 -->
      <g class="expertise-part" data-part="front_bumper" tabindex="0" role="button" aria-label="Ön tampon">
        <polygon points="210,70 248,55 262,55 262,155 248,170 218,155"></polygon>
      </g>
      <g class="expertise-part" data-part="fl_fender" tabindex="0" role="button" aria-label="Sol ön çamurluk">
        <polygon points="262,55 378,48 386,90 386,170 360,190 268,190 262,155"></polygon>
      </g>
      <g class="expertise-part" data-part="fl_door" tabindex="0" role="button" aria-label="Sol ön kapı">
        <polygon points="378,48 520,42 528,90 528,190 386,190 386,90"></polygon>
      </g>
      <g class="expertise-part" data-part="rl_door" tabindex="0" role="button" aria-label="Sol arka kapı">
        <polygon points="520,42 650,48 658,90 658,190 528,190 528,90"></polygon>
      </g>
      <g class="expertise-part" data-part="rl_quarter" tabindex="0" role="button" aria-label="Sol arka çamurluk">
        <polygon points="650,48 778,55 790,90 790,155 760,190 658,190 658,90"></polygon>
      </g>
      <g class="expertise-part" data-part="rear_bumper" tabindex="0" role="button" aria-label="Arka tampon">
        <polygon points="778,55 840,70 864,95 858,145 820,165 790,155 790,90"></polygon>
      </g>
      <g class="expertise-part" data-part="roof" tabindex="0" role="button" aria-label="Tavan">
        <polygon points="400,18 620,18 640,48 385,48"></polygon>
      </g>

      <!-- ÖN (orta sol): ~32,254–348,440 -->
      <g class="expertise-part" data-part="hood" tabindex="0" role="button" aria-label="Kaput">
        <polygon points="95,275 295,275 280,345 110,345"></polygon>
      </g>
      <g class="expertise-part" data-part="front_bumper" tabindex="0" role="button" aria-label="Ön tampon">
        <polygon points="70,345 320,345 335,420 55,420"></polygon>
      </g>
      <g class="expertise-part" data-part="fl_fender" tabindex="0" role="button" aria-label="Sol ön çamurluk">
        <polygon points="40,295 95,275 110,345 70,345 55,330"></polygon>
      </g>
      <g class="expertise-part" data-part="fr_fender" tabindex="0" role="button" aria-label="Sağ ön çamurluk">
        <polygon points="295,275 340,295 335,330 320,345 280,345"></polygon>
      </g>

      <!-- ÜST (orta): ~350,234–668,458 — ön üstte -->
      <g class="expertise-part" data-part="hood" tabindex="0" role="button" aria-label="Kaput">
        <polygon points="405,250 615,250 605,320 415,320"></polygon>
      </g>
      <g class="expertise-part" data-part="roof" tabindex="0" role="button" aria-label="Tavan">
        <polygon points="420,320 600,320 595,385 425,385"></polygon>
      </g>
      <g class="expertise-part" data-part="trunk" tabindex="0" role="button" aria-label="Bagaj kapağı">
        <polygon points="415,385 605,385 615,448 405,448"></polygon>
      </g>

      <!-- ARKA (orta sağ): ~670,252–1004,442 -->
      <g class="expertise-part" data-part="trunk" tabindex="0" role="button" aria-label="Bagaj kapağı">
        <polygon points="740,275 940,275 925,345 755,345"></polygon>
      </g>
      <g class="expertise-part" data-part="rear_bumper" tabindex="0" role="button" aria-label="Arka tampon">
        <polygon points="715,345 965,345 980,420 700,420"></polygon>
      </g>
      <g class="expertise-part" data-part="rl_quarter" tabindex="0" role="button" aria-label="Sol arka çamurluk">
        <polygon points="685,295 740,275 755,345 715,345 700,330"></polygon>
      </g>
      <g class="expertise-part" data-part="rr_quarter" tabindex="0" role="button" aria-label="Sağ arka çamurluk">
        <polygon points="940,275 990,295 980,330 965,345 925,345"></polygon>
      </g>

      <!-- SAĞ YAN (alt): burun sağa — kutu ~184,450–808,666 -->
      <g class="expertise-part" data-part="rear_bumper" tabindex="0" role="button" aria-label="Arka tampon">
        <polygon points="184,520 230,505 250,505 250,600 230,620 195,600"></polygon>
      </g>
      <g class="expertise-part" data-part="rr_quarter" tabindex="0" role="button" aria-label="Sağ arka çamurluk">
        <polygon points="250,505 368,498 378,535 378,620 350,640 258,640 250,600"></polygon>
      </g>
      <g class="expertise-part" data-part="rr_door" tabindex="0" role="button" aria-label="Sağ arka kapı">
        <polygon points="368,498 500,492 510,535 510,640 378,640 378,535"></polygon>
      </g>
      <g class="expertise-part" data-part="fr_door" tabindex="0" role="button" aria-label="Sağ ön kapı">
        <polygon points="500,492 638,498 648,535 648,640 510,640 510,535"></polygon>
      </g>
      <g class="expertise-part" data-part="fr_fender" tabindex="0" role="button" aria-label="Sağ ön çamurluk">
        <polygon points="638,498 748,505 760,535 760,600 735,640 648,640 648,535"></polygon>
      </g>
      <g class="expertise-part" data-part="front_bumper" tabindex="0" role="button" aria-label="Ön tampon">
        <polygon points="748,505 790,520 808,545 802,590 770,615 760,600 760,535"></polygon>
      </g>
      <g class="expertise-part" data-part="roof" tabindex="0" role="button" aria-label="Tavan">
        <polygon points="400,455 620,455 640,492 385,492"></polygon>
      </g>
    </svg>
  </div>

  <div class="expertise-diagram__legend">
    <?php foreach ($statusColors as $label => $color): ?>
      <?php $abbr = $statusAbbrevs[$label] ?? $label; ?>
      <span class="expertise-diagram__legend-item">
        <i style="background:<?= cx_e($color) ?>"><?= cx_e($abbr) ?></i><?= cx_e($label) ?> (<?= cx_e($abbr) ?>)
      </span>
    <?php endforeach; ?>
  </div>

  <?php if (!$expertiseReadonly): ?>
  <div class="expertise-diagram__picker" data-expertise-picker hidden>
    <div class="expertise-diagram__picker-title" data-expertise-picker-title>Parça</div>
    <div class="expertise-diagram__statuses">
      <?php foreach ($statuses as $st): ?>
        <?php $abbr = $statusAbbrevs[$st] ?? $st; ?>
        <button
          type="button"
          class="expertise-diagram__status"
          data-status="<?= cx_e($st) ?>"
          title="<?= cx_e($st) ?> (<?= cx_e($abbr) ?>)"
          aria-label="<?= cx_e($st) ?>"
          style="--st:<?= cx_e($statusColors[$st] ?? '#888') ?>"
        >
          <?= cx_e($st) ?> (<?= cx_e($abbr) ?>)
        </button>
      <?php endforeach; ?>
      <button type="button" class="expertise-diagram__status expertise-diagram__status--clear" data-status="">Temizle</button>
    </div>
  </div>
  <?php endif; ?>

  <ul class="expertise-diagram__summary" data-expertise-summary></ul>

  <div class="expertise-diagram__inputs" data-expertise-inputs hidden>
    <?php foreach ($partLabels as $partId => $label): ?>
      <?php $val = (string) ($expertiseParts[$partId] ?? ''); ?>
      <input type="hidden" name="expertise_parts[<?= cx_e($partId) ?>]" value="<?= cx_e($val) ?>" data-part-input="<?= cx_e($partId) ?>" data-part-label="<?= cx_e($label) ?>">
    <?php endforeach; ?>
  </div>

  <script type="application/json" data-expertise-meta><?= json_encode([
      'parts' => $partLabels,
      'colors' => $statusColors,
      'abbrevs' => $statusAbbrevs,
      'readonly' => $expertiseReadonly,
  ], JSON_UNESCAPED_UNICODE) ?></script>
</div>
