<?php

declare(strict_types=1);

/** @var list<array{label:string,href:string}> $breadcrumbs */
/** @var string|null $seoH1 */

$breadcrumbs = $breadcrumbs ?? [];
if ($breadcrumbs === []) {
    return;
}
?>
<nav class="seo-breadcrumbs" aria-label="Sayfa yolu">
  <?php foreach ($breadcrumbs as $i => $crumb): ?>
    <?php if ($i > 0): ?><span class="seo-breadcrumbs__sep">›</span><?php endif; ?>
    <?php if ($i === count($breadcrumbs) - 1): ?>
      <span class="seo-breadcrumbs__current"><?= cx_e($crumb['label']) ?></span>
    <?php else: ?>
      <a class="seo-breadcrumbs__link" href="<?= cx_e($crumb['href']) ?>"><?= cx_e($crumb['label']) ?></a>
    <?php endif; ?>
  <?php endforeach; ?>
</nav>
