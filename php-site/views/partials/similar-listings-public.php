<?php

declare(strict_types=1);

/** @var list<array<string,mixed>> $similarItems */
/** @var string $similarContext */
/** @var array<string,mixed>|null $user */
/** @var array<string,mixed> $app */
/** @var int $id */

$similarItems = $similarItems ?? [];
$similarContext = trim((string) ($similarContext ?? ''));
$user = $user ?? null;
$app = $app ?? cx_app_config();
$id = (int) ($id ?? 0);

if ($similarItems === []) {
    return;
}
?>
<section class="listing-similar" aria-label="Benzer ilanlar">
  <div class="listing-similar__head">
    <h2 class="listing-similar__title">Benzer ilanlar</h2>
    <?php if ($similarContext !== ''): ?>
      <p class="listing-similar__sub"><?= cx_e($similarContext) ?> — benzer km ve özellikler</p>
    <?php else: ?>
      <p class="listing-similar__sub">Aynı segmentte benzer özellikte diğer ilanlar</p>
    <?php endif; ?>
  </div>
  <?php
    $items = $similarItems;
    $vehicleBrowse = true;
    $favBack = '/listing.php?id=' . $id;
    require __DIR__ . '/market-listings-grid.php';
  ?>
</section>
