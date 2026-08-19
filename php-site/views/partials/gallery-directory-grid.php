<?php

declare(strict_types=1);

/** @var list<array<string,mixed>> $galleries */
/** @var array<string,mixed> $app */

$galleries = $galleries ?? [];
$app = $app ?? cx_app_config();
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');
?>
<div class="gallery-directory__grid">
  <?php if ($galleries === []): ?>
    <p class="gallery-directory__empty">Bu filtreye uygun mağaza bulunamadı.</p>
  <?php else: ?>
    <?php foreach ($galleries as $g):
        $gid = (int) ($g['id'] ?? 0);
        $name = (string) ($g['display_name'] ?? $g['username'] ?? 'Galeri');
        $logo = cx_user_avatar_src((string) ($g['avatar_url'] ?? ''), $uploadsUrl);
        $city = trim((string) ($g['city'] ?? ''));
        $isVip = ((string) ($g['role'] ?? '')) === 'vip_kurumsal';
        $verified = cx_gallery_is_verified($g);
        $st = is_array($g['stats'] ?? null) ? $g['stats'] : [];
        $listingN = (int) ($st['listings'] ?? ($g['live_count'] ?? 0));
        $new30 = (int) ($st['new_last_30'] ?? 0);
        $url = (string) ($g['public_url'] ?? ('/galeri.php?id=' . $gid));
        $about = trim((string) ($g['about'] ?? ''));
    ?>
    <a class="gallery-directory-card<?= $isVip ? ' gallery-directory-card--vip' : '' ?>" href="<?= cx_e($url) ?>">
      <div class="gallery-directory-card__logo<?= $logo === '' ? ' gallery-directory-card__logo--mono' : '' ?>">
        <?php if ($logo !== ''): ?>
          <img src="<?= cx_e($logo) ?>" alt="">
        <?php else: ?>
          <span><?= cx_e(mb_strtoupper(mb_substr($name, 0, 1))) ?></span>
        <?php endif; ?>
      </div>
      <div class="gallery-directory-card__body">
        <div class="gallery-directory-card__top">
          <strong><?= cx_e($name) ?></strong>
          <?php if ($verified): ?><span class="gallery-directory-card__badge">✓ Doğrulanmış</span><?php elseif ($isVip): ?><span class="gallery-directory-card__badge">VIP</span><?php else: ?><span class="gallery-directory-card__badge">Kurumsal</span><?php endif; ?>
        </div>
        <?php if ($city !== ''): ?><div class="gallery-directory-card__meta">📍 <?= cx_e($city) ?></div><?php endif; ?>
        <div class="gallery-directory-card__meta"><?= $listingN ?> aktif araç<?php if ($new30 > 0): ?> · son 30 günde <?= $new30 ?> yeni<?php endif; ?></div>
        <?php if ($about !== ''): ?>
          <p class="gallery-directory-card__about"><?= cx_e(mb_substr($about, 0, 120)) ?><?= mb_strlen($about) > 120 ? '…' : '' ?></p>
        <?php endif; ?>
      </div>
    </a>
    <?php endforeach; ?>
  <?php endif; ?>
</div>
