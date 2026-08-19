<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingWriteService.php';
require_once __DIR__ . '/app/Services/SellerPublicService.php';

use App\Helpers\Security;
use App\Services\ListingWriteService;
use App\Services\SellerPublicService;

cx_bootstrap();
$user = cx_require_user();

if (!cx_is_corporate($user)) {
    cx_flash('error', 'Mağaza paneli yalnızca kurumsal galeri hesapları içindir.');
    cx_redirect('/my-listings.php');
}

$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$writer = new ListingWriteService();
$sellerSvc = new SellerPublicService($base);
$back = '/gallery-panel.php';
$uid = (int) $user['id'];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    if (isset($_POST['cancel_id'])) {
        $lid = (int) $_POST['cancel_id'];
        if ($writer->cancel($lid, $uid, false)) {
            cx_flash('ok', 'İlan iptal edildi.');
        } else {
            cx_flash('error', 'İlan iptal edilemedi.');
        }
        cx_redirect($back . '?tab=listings');
    } elseif (isset($_POST['save_gallery_profile'])) {
        $okProfile = $sellerSvc->updateCorporateProfile($uid, [
            'gallery_name' => (string) ($_POST['gallery_name'] ?? ''),
            'phone' => (string) ($_POST['phone'] ?? ''),
            'city' => (string) ($_POST['city'] ?? ''),
            'email' => (string) ($_POST['email'] ?? ''),
            'website' => (string) ($_POST['website'] ?? ''),
            'about' => (string) ($_POST['about'] ?? ''),
            'gallery_hours' => cx_gallery_hours_from_post($_POST),
        ]);
        $logoOk = true;
        $logoMsg = '';
        $bannerOk = true;
        $bannerMsg = '';
        if (!empty($_POST['remove_logo'])) {
            $logoOk = $sellerSvc->updateAvatar($uid, '');
            $logoMsg = ' Logo kaldırıldı.';
        } elseif (!empty($_FILES['gallery_logo']['name'])) {
            $saved = cx_save_uploaded_gallery_logo($_FILES['gallery_logo'], $uid);
            $logoOk = $saved !== null && $sellerSvc->updateAvatar($uid, $saved);
            $logoMsg = $logoOk ? ' Logo güncellendi.' : '';
        }
        if (!empty($_POST['remove_banner'])) {
            $bannerOk = $sellerSvc->updateGalleryBanner($uid, '');
            $bannerMsg = ' Vitrin kaldırıldı.';
        } elseif (!empty($_FILES['gallery_banner']['name'])) {
            $savedBanner = cx_save_uploaded_gallery_banner($_FILES['gallery_banner'], $uid);
            $bannerOk = $savedBanner !== null && $sellerSvc->updateGalleryBanner($uid, $savedBanner);
            $bannerMsg = $bannerOk ? ' Vitrin güncellendi.' : '';
        }
        if ($okProfile && $logoOk && $bannerOk) {
            cx_flash('ok', 'Mağaza bilgileri kaydedildi.' . $logoMsg . $bannerMsg);
        } elseif (!$okProfile) {
            cx_flash('error', 'Profil kaydedilemedi. E-posta / web sitesini kontrol edin.');
        } elseif (!$logoOk) {
            cx_flash('error', 'Bilgiler kaydedildi ama logo işlemi başarısız (JPG/PNG/WEBP).');
        } else {
            cx_flash('error', 'Bilgiler kaydedildi ama vitrin görseli yüklenemedi (JPG/PNG/WEBP, max ~8MB).');
        }
        cx_redirect($back . '?tab=info');
    }
    cx_redirect($back);
}

$rows = $writer->mine($uid);
$siteUrl = (string) ($app['url'] ?? '');
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');
$quota = cx_user_listing_quota($user);
$publicGalleryUrl = '/galeri.php?id=' . $uid;
$ownerProfile = $sellerSvc->findOwner($uid) ?? [];
$logoSrc = cx_user_avatar_src((string) (($ownerProfile['avatar_url'] ?? '') ?: ''), $uploadsUrl);
$bannerSrc = cx_user_avatar_src((string) (($ownerProfile['gallery_banner'] ?? '') ?: ''), $uploadsUrl);

$counts = [
    'all' => count($rows),
    'active' => 0,
    'pending' => 0,
    'sold' => 0,
    'other' => 0,
];
foreach ($rows as $item) {
    $st = strtoupper((string) ($item['status'] ?? ''));
    if (in_array($st, ['APPROVED', 'ACTIVE'], true)) {
        $counts['active']++;
    } elseif (in_array($st, ['PENDING_MODERATION', 'PENDING'], true)) {
        $counts['pending']++;
    } elseif (cx_listing_is_sold($st)) {
        $counts['sold']++;
    } else {
        $counts['other']++;
    }
}

$filter = strtolower(trim((string) ($_GET['f'] ?? 'all')));
if (!in_array($filter, ['all', 'active', 'pending', 'sold'], true)) {
    $filter = 'all';
}

$tab = strtolower(trim((string) ($_GET['tab'] ?? 'info')));
if (!in_array($tab, ['info', 'listings'], true)) {
    $tab = 'info';
}
if (isset($_GET['f'])) {
    $tab = 'listings';
}

$filtered = array_values(array_filter($rows, static function (array $item) use ($filter): bool {
    if ($filter === 'all') {
        return true;
    }
    $st = strtoupper((string) ($item['status'] ?? ''));
    if ($filter === 'active') {
        return in_array($st, ['APPROVED', 'ACTIVE'], true);
    }
    if ($filter === 'pending') {
        return in_array($st, ['PENDING_MODERATION', 'PENDING'], true);
    }
    if ($filter === 'sold') {
        return cx_listing_is_sold($st);
    }

    return true;
}));

$isVip = cx_is_vip_kurumsal($user);
$galleryHours = cx_gallery_hours_normalize($ownerProfile['gallery_hours'] ?? []);
$galleryName = (string) ($ownerProfile['gallery_name'] ?? '');
if ($galleryName === '') {
    $galleryName = (string) ($ownerProfile['display_name'] ?? $user['username'] ?? '');
}
$vipMembership = cx_vip_membership_summary($ownerProfile);

ob_start();
?>
<div class="vip-panel">
  <header class="vip-panel__head">
    <div>
      <p class="vip-panel__eyebrow"><?= $isVip ? 'VIP Kurumsal' : 'Kurumsal galeri' ?></p>
      <h1 class="section-title">Mağaza paneli</h1>
      <p class="section-sub">Mağaza sayfanız, logo, iletişim, çalışma saatleri ve araç ilanlarını buradan yönetin.</p>
    </div>
    <div class="vip-panel__head-actions">
      <a class="btn-primary vip-panel__cta" href="<?= cx_e($publicGalleryUrl) ?>" target="_blank" rel="noopener">Mağazamı aç</a>
      <a class="btn-sm btn-sm--gold vip-panel__cta-secondary" href="/create-listing.php">+ Yeni ilan</a>
    </div>
  </header>

  <nav class="vip-panel__tabs" aria-label="Panel sekmeleri">
    <a class="vip-panel__tab<?= $tab === 'info' ? ' is-active' : '' ?>" href="?tab=info">Mağaza bilgileri</a>
    <a class="vip-panel__tab<?= $tab === 'listings' ? ' is-active' : '' ?>" href="?tab=listings">İlanlarım</a>
  </nav>

  <?php if ($tab === 'info'): ?>
  <?php if ($isVip): ?>
  <section class="vip-panel__membership<?= $vipMembership['expired'] ? ' is-expired' : ($vipMembership['active'] ? ' is-active' : '') ?>" aria-label="VIP üyelik">
    <h2 class="vip-panel__section-title">VIP üyelik süresi</h2>
    <p class="vip-panel__section-sub">Başlangıç ve bitiş tarihleri yalnızca yönetim tarafından belirlenir; siz değiştiremezsiniz.</p>
    <dl class="vip-panel__membership-grid">
      <div>
        <dt>Başlangıç</dt>
        <dd><?= $vipMembership['starts'] !== '' ? cx_e($vipMembership['starts']) : '—' ?></dd>
      </div>
      <div>
        <dt>Bitiş</dt>
        <dd><?= $vipMembership['ends'] !== '' ? cx_e($vipMembership['ends']) : '—' ?></dd>
      </div>
      <div>
        <dt>Durum</dt>
        <dd><span class="vip-panel__membership-status"><?= cx_e($vipMembership['status_label']) ?></span></dd>
      </div>
    </dl>
  </section>
  <?php endif; ?>

  <section class="vip-panel__profile" id="galeri-bilgileri">
    <h2 class="vip-panel__section-title">Mağaza kimliği, logo ve vitrin</h2>
    <p class="vip-panel__section-sub">Herkese açık mağaza sayfanızda görünen ad, iletişim, çalışma saatleri, logo ve vitrin. Kaydettikten sonra “Mağazamı aç” ile kontrol edin.</p>

    <form class="vip-panel__profile-form" method="post" enctype="multipart/form-data">
      <?= cx_csrf_field() ?>
      <input type="hidden" name="save_gallery_profile" value="1">

      <div class="vip-panel__banner-box">
        <div class="vip-panel__banner-preview<?= $bannerSrc === '' ? ' vip-panel__banner-preview--empty' : '' ?>">
          <?php if ($bannerSrc !== ''): ?>
            <img src="<?= cx_e($bannerSrc) ?>" alt="Vitrin görseli">
          <?php else: ?>
            <span>Vitrin görseli yok — varsayılan olarak ilan fotoğrafı kullanılır</span>
          <?php endif; ?>
        </div>
        <div class="vip-panel__logo-fields">
          <p class="vip-panel__logo-title">Mağaza vitrin görseli (arka plan)</p>
          <label class="vip-panel__logo-btn" for="gallery_banner">
            <?= $bannerSrc !== '' ? 'Vitrini değiştir' : 'Vitrin ekle' ?>
            <input id="gallery_banner" type="file" name="gallery_banner" accept="image/jpeg,image/png,image/webp">
          </label>
          <span class="vip-panel__hint">JPG, PNG veya WEBP. Yatay geniş görsel önerilir (ör. 1600×600).</span>
          <?php if ($bannerSrc !== ''): ?>
          <label class="vip-panel__check">
            <input type="checkbox" name="remove_banner" value="1">
            Özel vitrini kaldır (ilan fotoğrafına dön)
          </label>
          <?php endif; ?>
        </div>
      </div>

      <div class="vip-panel__logo-box">
        <div class="vip-panel__logo-preview vip-panel__logo-preview--lg<?= $logoSrc === '' ? ' vip-panel__logo-preview--empty' : '' ?>">
          <?php if ($logoSrc !== ''): ?>
            <img src="<?= cx_e($logoSrc) ?>" alt="Galeri logosu">
          <?php else: ?>
            <span>Logo yok</span>
          <?php endif; ?>
        </div>
        <div class="vip-panel__logo-fields">
          <p class="vip-panel__logo-title">Mağaza logosu</p>
          <label class="vip-panel__logo-btn" for="gallery_logo">
            <?= $logoSrc !== '' ? 'Logoyu değiştir' : 'Logo ekle' ?>
            <input id="gallery_logo" type="file" name="gallery_logo" accept="image/jpeg,image/png,image/webp">
          </label>
          <span class="vip-panel__hint">JPG, PNG veya WEBP. Önerilen kare görsel.</span>
          <?php if ($logoSrc !== ''): ?>
          <label class="vip-panel__check">
            <input type="checkbox" name="remove_logo" value="1">
            Mevcut logoyu kaldır
          </label>
          <?php endif; ?>
        </div>
      </div>

      <div class="vip-panel__profile-grid">
        <label class="vip-panel__field">
          <span>Mağaza adı</span>
          <input class="create-input" type="text" name="gallery_name" maxlength="128" required
                 value="<?= cx_e($galleryName) ?>" placeholder="Örn. Fer Motors">
        </label>
        <label class="vip-panel__field">
          <span>Telefon</span>
          <input class="create-input" type="tel" name="phone" maxlength="32"
                 value="<?= cx_e((string) ($ownerProfile['phone'] ?? '')) ?>" placeholder="0533 123 45 67">
        </label>
        <label class="vip-panel__field">
          <span>Şehir</span>
          <input class="create-input" type="text" name="city" maxlength="128"
                 value="<?= cx_e((string) ($ownerProfile['city'] ?? '')) ?>" placeholder="Lefkoşa / İstanbul">
        </label>
        <label class="vip-panel__field">
          <span>E-posta</span>
          <input class="create-input" type="email" name="email" maxlength="255"
                 value="<?= cx_e((string) ($ownerProfile['email'] ?? '')) ?>" placeholder="galeri@ornek.com">
        </label>
        <label class="vip-panel__field vip-panel__field--wide">
          <span>Web sitesi</span>
          <input class="create-input" type="url" name="website" maxlength="255"
                 value="<?= cx_e((string) ($ownerProfile['website'] ?? '')) ?>" placeholder="https://">
        </label>
        <label class="vip-panel__field vip-panel__field--wide">
          <span>Kısa tanıtım (Hakkında)</span>
          <textarea class="create-input" name="about" rows="3" maxlength="500"
                    placeholder="Galeriniz hakkında kısa bilgi"><?= cx_e((string) ($ownerProfile['about'] ?? '')) ?></textarea>
        </label>
      </div>

      <fieldset class="vip-panel__hours">
        <legend>Çalışma saatleri</legend>
        <p class="vip-panel__hint">Mağaza sayfasında görünür. Kapalı günleri işaretleyin.</p>
        <div class="vip-panel__hours-grid">
          <?php foreach (cx_gallery_hour_days() as $dayKey => $dayLabel):
              $slot = is_array($galleryHours[$dayKey] ?? null) ? $galleryHours[$dayKey] : null;
              $closed = $slot === null;
              $openVal = $slot['open'] ?? '09:00';
              $closeVal = $slot['close'] ?? '18:00';
          ?>
          <div class="vip-panel__hours-row">
            <span class="vip-panel__hours-day"><?= cx_e($dayLabel) ?></span>
            <label class="vip-panel__check">
              <input type="checkbox" name="hours[<?= cx_e($dayKey) ?>][closed]" value="1"<?= $closed ? ' checked' : '' ?>>
              Kapalı
            </label>
            <input class="create-input" type="time" name="hours[<?= cx_e($dayKey) ?>][open]" value="<?= cx_e($openVal) ?>">
            <span class="vip-panel__hours-sep">–</span>
            <input class="create-input" type="time" name="hours[<?= cx_e($dayKey) ?>][close]" value="<?= cx_e($closeVal) ?>">
          </div>
          <?php endforeach; ?>
        </div>
      </fieldset>

      <div class="vip-panel__profile-actions">
        <button class="btn-primary" type="submit">Mağaza bilgilerini kaydet</button>
        <a class="link-gold" href="<?= cx_e($publicGalleryUrl) ?>" target="_blank" rel="noopener">Mağazayı önizle →</a>
      </div>
    </form>
  </section>
  <?php else: ?>

  <?php if ($quota['message'] !== ''): ?>
  <p class="vip-panel__quota"><?= cx_e($quota['message']) ?></p>
  <?php endif; ?>

  <div class="vip-panel__stats" aria-label="İlan özeti">
    <div class="vip-panel__stat"><strong><?= (int) $counts['all'] ?></strong><span>Toplam</span></div>
    <div class="vip-panel__stat"><strong><?= (int) $counts['active'] ?></strong><span>Yayında</span></div>
    <div class="vip-panel__stat"><strong><?= (int) $counts['pending'] ?></strong><span>Onayda</span></div>
    <div class="vip-panel__stat"><strong><?= (int) $counts['sold'] ?></strong><span>Satıldı</span></div>
  </div>

  <div class="vip-panel__filters" role="tablist" aria-label="Filtre">
    <a class="vip-panel__filter<?= $filter === 'all' ? ' is-active' : '' ?>" href="?tab=listings&amp;f=all">Tümü</a>
    <a class="vip-panel__filter<?= $filter === 'active' ? ' is-active' : '' ?>" href="?tab=listings&amp;f=active">Yayında</a>
    <a class="vip-panel__filter<?= $filter === 'pending' ? ' is-active' : '' ?>" href="?tab=listings&amp;f=pending">Onayda</a>
    <a class="vip-panel__filter<?= $filter === 'sold' ? ' is-active' : '' ?>" href="?tab=listings&amp;f=sold">Satıldı</a>
  </div>

  <?php if ($filtered === []): ?>
  <p class="empty-state">Bu filtrede ilan yok. <a class="link-gold" href="/create-listing.php">İlan ekle</a></p>
  <?php else: ?>
  <div class="mine-list vip-panel__list">
  <?php foreach ($filtered as $item):
      $no = cx_listing_no((int) $item['id'], $base);
      $st = strtoupper((string) ($item['status'] ?? ''));
      $photos = cx_photo_urls($item['photo_urls'] ?? '[]', $uploadsUrl);
      $thumb = $photos[0] ?? '';
      $expired = !empty($item['is_expired']);
  ?>
    <article class="mine-row<?= cx_listing_is_sold($st) ? ' mine-row--sold' : '' ?>">
      <div class="mine-row__media">
        <?php if ($thumb): ?>
          <?= cx_photo_img($thumb, 'thumb', ['class' => 'mine-row__img', 'alt' => ''], $siteUrl, $uploadsUrl) ?>
        <?php else: ?>
          <div class="mine-row__img mine-row__img--empty">Foto yok</div>
        <?php endif; ?>
        <?php if (cx_listing_is_sold($st)): ?><span class="mine-row__ribbon">SATILDI</span><?php endif; ?>
      </div>
      <div class="mine-row__body">
        <div class="mine-row__status"><?= cx_listing_status_emoji($st) ?> <?= cx_e(cx_listing_status_label($st)) ?></div>
        <h3 class="mine-row__title"><a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_e($item['title']) ?></a></h3>
        <div class="mine-row__meta">#<?= $no ?> · 👁 <?= (int) ($item['view_count'] ?? 0) ?> · ❤️ <?= (int) ($item['favorite_count'] ?? 0) ?> · 📅 <?= (int) ($item['days_live'] ?? 0) ?> gün</div>
        <?php if (!cx_listing_can_adjust_price($item)): ?>
        <div class="mine-row__price"><?= cx_e(cx_listing_price_line($item)) ?></div>
        <?php endif; ?>
        <?php
          $priceAdjustBack = '/gallery-panel.php?tab=listings';
          require __DIR__ . '/views/partials/price-adjust.php';
          unset($priceAdjustBack);
        ?>
        <?php if ($expired): ?>
          <div class="mine-row__alert">⚠️ Bu ilanın süresi doldu.</div>
        <?php endif; ?>
      </div>
      <div class="mine-row__actions">
        <a class="btn-sm" href="/listing.php?id=<?= (int) $item['id'] ?>">Detay</a>
        <?php if (!in_array($st, ['CANCELLED', 'SOLD'], true)): ?>
        <a class="btn-sm btn-sm--gold" href="/edit-listing.php?id=<?= (int) $item['id'] ?>">Düzenle</a>
        <?php endif; ?>
        <?php if (in_array($st, ['APPROVED', 'ACTIVE'], true)): ?>
        <form method="post" action="/listing-action.php" style="display:inline" onsubmit="return confirm('Bu ilan satıldı olarak işaretlenecek. Devam?')">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="action" value="mark_sold">
          <input type="hidden" name="listing_id" value="<?= (int) $item['id'] ?>">
          <input type="hidden" name="back" value="<?= cx_e($back . '?tab=listings') ?>">
          <button class="btn-sm" type="submit">Satıldı</button>
        </form>
        <?php endif; ?>
        <?php if ($expired): ?>
        <form method="post" action="/listing-action.php" style="display:inline">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="action" value="republish">
          <input type="hidden" name="listing_id" value="<?= (int) $item['id'] ?>">
          <input type="hidden" name="back" value="<?= cx_e($back . '?tab=listings') ?>">
          <button class="btn-sm btn-sm--gold" type="submit">Yeniden yayınla</button>
        </form>
        <?php endif; ?>
        <?php if ($st !== 'CANCELLED'): ?>
        <form method="post" style="display:inline">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="cancel_id" value="<?= (int) $item['id'] ?>">
          <button class="btn-sm" type="submit" onclick="return confirm('İlan iptal edilsin mi?')">İptal</button>
        </form>
        <?php endif; ?>
      </div>
    </article>
  <?php endforeach; ?>
  </div>
  <?php endif; ?>
  <?php endif; ?>
</div>
<?php
$content = ob_get_clean();
$title = 'Mağaza paneli';
$layout = 'app';
$navActive = 'gallery';
require __DIR__ . '/views/layout.php';
