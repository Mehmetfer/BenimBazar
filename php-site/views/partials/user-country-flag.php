<?php
declare(strict_types=1);
/** @var string $country */
$country = cx_normalize_country((string) ($country ?? 'tr'));
$isKktc = $country === 'kktc';
$label = $isKktc ? 'KKTC' : 'Türkiye';
?>
<span class="user-country-flag" title="<?= cx_e($label) ?>">
  <?php if ($isKktc): ?>
  <svg class="user-country-flag__svg" viewBox="0 0 36 24" width="28" height="18" role="img" aria-label="KKTC" focusable="false">
    <rect width="36" height="24" fill="#fff"/>
    <rect y="0" width="36" height="3.2" fill="#e30a17"/>
    <rect y="20.8" width="36" height="3.2" fill="#e30a17"/>
    <circle cx="14.2" cy="12" r="5.1" fill="#e30a17"/>
    <circle cx="15.7" cy="12" r="4.1" fill="#fff"/>
    <polygon fill="#e30a17" points="21.2,12 19.55,12.55 20.85,11.15 20.85,12.85 19.55,11.45"/>
  </svg>
  <?php else: ?>
  <svg class="user-country-flag__svg" viewBox="0 0 36 24" width="28" height="18" role="img" aria-label="Türkiye" focusable="false">
    <rect width="36" height="24" fill="#e30a17"/>
    <circle cx="13.5" cy="12" r="6" fill="#fff"/>
    <circle cx="15.4" cy="12" r="4.8" fill="#e30a17"/>
    <polygon fill="#fff" points="21.6,12 19.55,12.7 20.95,10.9 20.95,13.1 19.55,11.3"/>
  </svg>
  <?php endif; ?>
  <span class="user-country-flag__label"><?= cx_e($label) ?></span>
</span>
