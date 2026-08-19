<?php

declare(strict_types=1);

/** @var string $trustTitle */
/** @var string $trustLead */
/** @var list<array{q:string,a:string}>|null $trustFaq */

$trustTitle = $trustTitle ?? 'BenimBazar';
$trustLead = $trustLead ?? '';
$trustFaq = $trustFaq ?? null;
?>
<section class="trust-page">
  <h1><?= cx_e($trustTitle) ?></h1>
  <?php if ($trustLead !== ''): ?>
  <p class="trust-page__lead"><?= cx_e($trustLead) ?></p>
  <?php endif; ?>
  <div class="trust-page__body">
    <?= $trustBody ?? '' ?>
  </div>
  <?php if (is_array($trustFaq) && $trustFaq !== []): ?>
  <div class="trust-page__faq">
    <h2>Sık sorulan sorular</h2>
    <?php foreach ($trustFaq as $row): ?>
    <details class="trust-faq__item">
      <summary><?= cx_e((string) ($row['q'] ?? '')) ?></summary>
      <p><?= cx_e((string) ($row['a'] ?? '')) ?></p>
    </details>
    <?php endforeach; ?>
  </div>
  <?php endif; ?>
</section>
