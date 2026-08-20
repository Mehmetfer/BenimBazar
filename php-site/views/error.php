<?php
declare(strict_types=1);
/** @var string $title */
/** @var string $publicMsg */
/** @var string $hint */
?>
<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= htmlspecialchars((string) ($title ?? 'Gecici sorun'), ENT_QUOTES, 'UTF-8') ?> — <?= htmlspecialchars(function_exists('cx_site_name') ? cx_site_name() : 'BenimBazar', ENT_QUOTES, 'UTF-8') ?></title>
  <style>
    body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0d0f14;color:#f5f5f5;font-family:Montserrat,system-ui,sans-serif;padding:1.5rem}
    .box{max-width:32rem;text-align:center;border:1px solid #2a3140;border-radius:16px;padding:2rem;background:#12151c}
    h1{margin:0 0 .75rem;font-size:1.35rem}
    p{margin:.5rem 0;line-height:1.5}
    .muted{opacity:.75;font-size:.95rem}
    a{color:#6fbf4a}
  </style>
</head>
<body>
  <div class="box">
    <h1><?= htmlspecialchars((string) ($title ?? 'Gecici sorun'), ENT_QUOTES, 'UTF-8') ?></h1>
    <p><?= htmlspecialchars((string) ($publicMsg ?? 'Gecici bir sorun olustu.'), ENT_QUOTES, 'UTF-8') ?></p>
    <p class="muted"><?= htmlspecialchars((string) ($hint ?? 'Lutfen birkac dakika sonra tekrar deneyin.'), ENT_QUOTES, 'UTF-8') ?></p>
    <p><a href="/index.php">Ana sayfaya don</a></p>
  </div>
</body>
</html>
