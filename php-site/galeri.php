<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SellerPublicService.php';
require_once __DIR__ . '/app/Services/SocialService.php';

use App\Services\SellerPublicService;

cx_bootstrap();

$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$ownerId = (int) ($_GET['id'] ?? 0);
$user = cx_current_user();
$svc = new SellerPublicService($base);
$owner = $svc->findOwner($ownerId);

if ($owner === null) {
    cx_flash('error', 'Galeri bulunamadı.');
    cx_redirect('/index.php');
}

if (empty($owner['is_corporate'])) {
    cx_redirect('/satici.php?id=' . $ownerId);
}

$isVip = ((string) ($owner['role'] ?? '')) === 'vip_kurumsal';
$allItems = $svc->publicListings($ownerId, $user ? (int) $user['id'] : null, true);
$stats = $svc->galleryStats($owner, $allItems, $user ? (int) $user['id'] : null);

$displayName = (string) ($owner['display_name'] ?? $owner['username'] ?? 'Galeri');
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');
$siteUrl = rtrim((string) ($app['url'] ?? ''), '/');
$logoSrc = cx_user_avatar_src((string) ($owner['avatar_url'] ?? ''), $uploadsUrl);
$bannerRaw = (string) ($stats['banner'] ?? '');
$bannerSrc = '';
if ($bannerRaw !== '') {
    if (preg_match('#^https?://#i', $bannerRaw) || str_starts_with($bannerRaw, '/')) {
        $bannerSrc = $bannerRaw;
    } else {
        $bannerSrc = cx_user_avatar_src($bannerRaw, $uploadsUrl);
    }
}

$phone = trim((string) ($owner['phone'] ?? ''));
$phoneDigits = preg_replace('/\D+/', '', $phone) ?? '';
$city = trim((string) ($owner['city'] ?? ''));
$website = trim((string) ($owner['website'] ?? ''));
$about = trim((string) ($owner['about'] ?? ''));
$email = trim((string) ($owner['email'] ?? ''));
$isOwnGallery = $user && (int) $user['id'] === $ownerId;
$storeUrl = ($siteUrl !== '' ? $siteUrl : '') . '/galeri.php?id=' . $ownerId;
$shareText = $displayName . ' — BenimBazar mağazası' . "\n" . $storeUrl;
$waShare = 'https://wa.me/?text=' . rawurlencode($shareText);
$waChat = $phoneDigits !== '' ? 'https://wa.me/' . $phoneDigits : $waShare;
$messagesHref = cx_messages_enabled() ? '/messages.php' : '';
$favBack = '/galeri.php?id=' . $ownerId;
$vehicleBrowse = true;

// Filtreler
$fCat = trim((string) ($_GET['cat'] ?? ''));
$fFuel = trim((string) ($_GET['fuel'] ?? ''));
$fGear = trim((string) ($_GET['gear'] ?? ''));
$fPrice = trim((string) ($_GET['price'] ?? ''));
$fSort = trim((string) ($_GET['sort'] ?? 'new'));
if (!in_array($fSort, ['new', 'price_asc', 'price_desc', 'views'], true)) {
    $fSort = 'new';
}

$categories = [];
$fuels = [];
$gears = [];
foreach ($allItems as $it) {
    $st = strtoupper((string) ($it['status'] ?? ''));
    if (!in_array($st, ['APPROVED', 'ACTIVE', 'SOLD'], true)) {
        continue;
    }
    $sub = trim((string) ($it['subcategory'] ?? $it['category'] ?? ''));
    if ($sub !== '') {
        $categories[$sub] = true;
    }
    $veh = cx_listing_attrs($it)['vehicle'] ?? [];
    if (is_array($veh)) {
        $fuel = trim((string) ($veh['fuel'] ?? ''));
        $gear = trim((string) ($veh['transmission'] ?? ''));
        if ($fuel !== '') {
            $fuels[$fuel] = true;
        }
        if ($gear !== '') {
            $gears[$gear] = true;
        }
    }
}
ksort($categories);
ksort($fuels);
ksort($gears);

$items = array_values(array_filter($allItems, static function (array $it) use ($fCat, $fFuel, $fGear, $fPrice): bool {
    $st = strtoupper((string) ($it['status'] ?? ''));
    if (!in_array($st, ['APPROVED', 'ACTIVE', 'SOLD'], true)) {
        return false;
    }
    if ($fCat !== '') {
        $sub = trim((string) ($it['subcategory'] ?? $it['category'] ?? ''));
        if ($sub !== $fCat) {
            return false;
        }
    }
    $veh = cx_listing_attrs($it)['vehicle'] ?? [];
    $veh = is_array($veh) ? $veh : [];
    if ($fFuel !== '' && trim((string) ($veh['fuel'] ?? '')) !== $fFuel) {
        return false;
    }
    if ($fGear !== '' && trim((string) ($veh['transmission'] ?? '')) !== $fGear) {
        return false;
    }
    if ($fPrice !== '') {
        $price = (float) ($it['price_tl'] ?? 0);
        if ($fPrice === '0-250000' && ($price <= 0 || $price > 250000)) {
            return false;
        }
        if ($fPrice === '250000-500000' && ($price < 250000 || $price > 500000)) {
            return false;
        }
        if ($fPrice === '500000-1000000' && ($price < 500000 || $price > 1000000)) {
            return false;
        }
        if ($fPrice === '1000000+' && $price < 1000000) {
            return false;
        }
    }

    return true;
}));

usort($items, static function (array $a, array $b) use ($fSort): int {
    if ($fSort === 'price_asc') {
        return ((float) ($a['price_tl'] ?? 0)) <=> ((float) ($b['price_tl'] ?? 0));
    }
    if ($fSort === 'price_desc') {
        return ((float) ($b['price_tl'] ?? 0)) <=> ((float) ($a['price_tl'] ?? 0));
    }
    if ($fSort === 'views') {
        return ((int) ($b['view_count'] ?? 0)) <=> ((int) ($a['view_count'] ?? 0));
    }

    return ((float) ($b['created_at'] ?? 0)) <=> ((float) ($a['created_at'] ?? 0));
});

$fmtInt = static function (int $n): string {
    return number_format($n, 0, ',', '.');
};

$aboutText = $about !== ''
    ? $about
    : ($isVip
        ? 'VIP Kurumsal galeri — güvenilir araç portföyü ve hızlı iletişim.'
        : 'Kurumsal galeri — araç ilanları BenimBazar’da.');

ob_start();
?>
<section class="store-page<?= $isVip ? ' store-page--vip' : '' ?>">
  <nav class="store-page__crumbs" aria-label="Sayfa yolu">
    <a href="/index.php">Ana sayfa</a>
    <span>›</span>
    <span>Mağazalar</span>
    <span>›</span>
    <span><?= cx_e($displayName) ?></span>
  </nav>

  <header class="store-hero">
    <div class="store-hero__bg" aria-hidden="true">
      <?php if ($bannerSrc !== ''): ?>
        <img src="<?= cx_e($bannerSrc) ?>" alt="">
      <?php endif; ?>
      <div class="store-hero__shade"></div>
    </div>

    <?php if (!$isOwnGallery): ?>
      <?php if ($user): ?>
      <form method="post" action="/follow-toggle.php" class="store-hero__follow">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="user_id" value="<?= $ownerId ?>">
        <input type="hidden" name="back" value="<?= cx_e($favBack) ?>">
        <button type="submit" class="store-hero__follow-btn<?= !empty($stats['is_following']) ? ' is-on' : '' ?>">
          <?= !empty($stats['is_following']) ? '♥ Takip ediliyor' : '♡ Mağazayı Takip Et' ?>
        </button>
      </form>
      <?php else: ?>
      <a class="store-hero__follow-btn store-hero__follow" href="<?= cx_e(cx_login_url($favBack, 'Takip için giriş yapın')) ?>">♡ Mağazayı Takip Et</a>
      <?php endif; ?>
    <?php endif; ?>

    <div class="store-hero__overlay">
      <div class="store-hero__logo<?= $logoSrc === '' ? ' store-hero__logo--mono' : '' ?>">
        <?php if ($logoSrc !== ''): ?>
          <img src="<?= cx_e($logoSrc) ?>" alt="<?= cx_e($displayName) ?> logosu">
        <?php else: ?>
          <span class="store-hero__mono"><?= cx_e(mb_strtoupper(mb_substr($displayName, 0, 1))) ?></span>
          <span class="store-hero__mono-name"><?= cx_e(mb_strtoupper($displayName)) ?></span>
        <?php endif; ?>
        <span class="store-hero__badge"><?= $isVip ? 'VIP Kurumsal' : 'Kurumsal Üye' ?></span>
      </div>

      <div class="store-hero__info">
        <h1 class="store-hero__name">
          <?= cx_e($displayName) ?>
          <?php if ($isVip): ?><span class="store-hero__verified" title="Doğrulanmış">✓</span><?php endif; ?>
        </h1>
        <?php if ($city !== ''): ?>
        <p class="store-hero__loc"><span aria-hidden="true">📍</span> <?= cx_e($city) ?></p>
        <?php endif; ?>
        <p class="store-hero__about"><?= cx_e($aboutText) ?></p>

        <div class="store-hero__stats" aria-label="Mağaza istatistikleri">
          <div class="store-hero__stat">
            <span class="store-hero__stat-ico" aria-hidden="true">🚗</span>
            <div><strong><?= cx_e($fmtInt((int) $stats['listings'])) ?></strong><span>İlan</span></div>
          </div>
          <div class="store-hero__stat">
            <span class="store-hero__stat-ico" aria-hidden="true">♥</span>
            <div><strong><?= cx_e($fmtInt((int) $stats['favorites'])) ?></strong><span>Favori</span></div>
          </div>
          <div class="store-hero__stat">
            <span class="store-hero__stat-ico" aria-hidden="true">👁</span>
            <div><strong><?= cx_e($fmtInt((int) $stats['views'])) ?></strong><span>Görüntülenme</span></div>
          </div>
          <div class="store-hero__stat">
            <span class="store-hero__stat-ico" aria-hidden="true">📅</span>
            <div><strong><?= (int) $stats['member_year'] ?></strong><span>Üyelik Tarihi</span></div>
          </div>
        </div>

        <div class="store-hero__actions">
          <?php
            $msgHref = '';
            if (!$isOwnGallery) {
                if (cx_messages_enabled()) {
                    $msgHref = $user ? '/messages.php' : cx_login_url($favBack, 'Mesaj için giriş yapın');
                } elseif ($email !== '') {
                    $msgHref = 'mailto:' . $email;
                } else {
                    $msgHref = $user ? '/messages.php' : cx_login_url($favBack, 'Mesaj için giriş yapın');
                }
            }
          ?>
          <?php if ($msgHref !== ''): ?>
          <a class="store-hero__btn store-hero__btn--primary" href="<?= cx_e($msgHref) ?>">Mesaj Gönder</a>
          <?php endif; ?>
          <?php if ($phone !== ''): ?>
          <a class="store-hero__btn" href="tel:<?= cx_e($phoneDigits !== '' ? $phoneDigits : $phone) ?>">Ara</a>
          <a class="store-hero__btn" href="<?= cx_e($waChat) ?>" target="_blank" rel="noopener">WhatsApp</a>
          <?php else: ?>
          <a class="store-hero__btn" href="<?= cx_e($waShare) ?>" target="_blank" rel="noopener">WhatsApp</a>
          <?php endif; ?>
          <a class="store-hero__btn" href="<?= cx_e($waShare) ?>" target="_blank" rel="noopener">Mağazayı Paylaş</a>
        </div>

        <?php if ($isOwnGallery && $isVip): ?>
        <p class="store-hero__owner-edit"><a href="/gallery-panel.php?tab=info">Mağaza bilgilerini düzenle →</a></p>
        <?php endif; ?>
      </div>
    </div>
  </header>

  <div class="store-trust" aria-label="Güven unsurları">
    <div class="store-trust__item">
      <span class="store-trust__ico" aria-hidden="true">🛡️</span>
      <div>
        <strong>Güvenilir Satıcı</strong>
        <span>Doğrulanmış Mağaza</span>
      </div>
    </div>
    <div class="store-trust__item">
      <span class="store-trust__ico" aria-hidden="true">⭐</span>
      <div>
        <strong>Müşteri Memnuniyeti</strong>
        <span>%98 Olumlu Geri Bildirim</span>
      </div>
    </div>
    <div class="store-trust__item">
      <span class="store-trust__ico" aria-hidden="true">🎧</span>
      <div>
        <strong>Hızlı İletişim</strong>
        <span>7/24 Destek</span>
      </div>
    </div>
    <div class="store-trust__item">
      <span class="store-trust__ico" aria-hidden="true">🚙</span>
      <div>
        <strong>Geniş Araç Portföyü</strong>
        <span>Farklı Marka ve Modeller</span>
      </div>
    </div>
  </div>

  <form class="store-filters" method="get" action="/galeri.php">
    <input type="hidden" name="id" value="<?= $ownerId ?>">
    <label class="store-filters__field">
      <span class="visually-hidden">Kategori</span>
      <select name="cat">
        <option value="">Tüm Kategoriler</option>
        <?php foreach (array_keys($categories) as $c): ?>
        <option value="<?= cx_e($c) ?>"<?= $fCat === $c ? ' selected' : '' ?>><?= cx_e($c) ?></option>
        <?php endforeach; ?>
      </select>
    </label>
    <label class="store-filters__field">
      <span class="visually-hidden">Fiyat</span>
      <select name="price">
        <option value="">Fiyat Aralığı</option>
        <option value="0-250000"<?= $fPrice === '0-250000' ? ' selected' : '' ?>>0 – 250.000 TL</option>
        <option value="250000-500000"<?= $fPrice === '250000-500000' ? ' selected' : '' ?>>250.000 – 500.000 TL</option>
        <option value="500000-1000000"<?= $fPrice === '500000-1000000' ? ' selected' : '' ?>>500.000 – 1.000.000 TL</option>
        <option value="1000000+"<?= $fPrice === '1000000+' ? ' selected' : '' ?>>1.000.000+ TL</option>
      </select>
    </label>
    <label class="store-filters__field">
      <span class="visually-hidden">Yakıt</span>
      <select name="fuel">
        <option value="">Tüm Yakıt Tipleri</option>
        <?php foreach (array_keys($fuels) as $fu): ?>
        <option value="<?= cx_e($fu) ?>"<?= $fFuel === $fu ? ' selected' : '' ?>><?= cx_e($fu) ?></option>
        <?php endforeach; ?>
      </select>
    </label>
    <label class="store-filters__field">
      <span class="visually-hidden">Vites</span>
      <select name="gear">
        <option value="">Tüm Vites Tipleri</option>
        <?php foreach (array_keys($gears) as $g): ?>
        <option value="<?= cx_e($g) ?>"<?= $fGear === $g ? ' selected' : '' ?>><?= cx_e($g) ?></option>
        <?php endforeach; ?>
      </select>
    </label>
    <button class="store-filters__submit" type="submit">Filtrele</button>
    <label class="store-filters__sort">
      <span>Sıralama</span>
      <select name="sort" onchange="this.form.submit()">
        <option value="new"<?= $fSort === 'new' ? ' selected' : '' ?>>Yeniden Eskiye</option>
        <option value="price_asc"<?= $fSort === 'price_asc' ? ' selected' : '' ?>>Fiyat (artan)</option>
        <option value="price_desc"<?= $fSort === 'price_desc' ? ' selected' : '' ?>>Fiyat (azalan)</option>
        <option value="views"<?= $fSort === 'views' ? ' selected' : '' ?>>Görüntülenme</option>
      </select>
    </label>
  </form>

  <div class="store-page__list-head">
    <h2 class="store-page__list-title">Mağaza ilanları</h2>
    <p class="store-page__list-count"><?= count($items) ?> ilan</p>
  </div>

  <?php
  require __DIR__ . '/views/partials/market-listings-grid.php';
  ?>
</section>
<?php
$content = ob_get_clean();
$title = $displayName . ' — Mağaza';
$layout = 'app';
$navActive = 'home';
$bodyClass = 'page-store' . ($isVip ? ' page-store--vip' : '');
require __DIR__ . '/views/layout.php';
