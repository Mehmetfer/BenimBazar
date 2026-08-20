<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingService.php';
require_once __DIR__ . '/app/Services/ShareCardService.php';

use App\Helpers\Security;
use App\Services\ListingService;
use App\Services\ShareCardService;

cx_bootstrap();

Security::rateLimit('share_card', 40, 300);

$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$id = (int) ($_GET['id'] ?? 0);
$format = (string) ($_GET['format'] ?? 'square');
$format = $format === 'story' ? 'story' : 'square';

$currentUser = cx_current_user();
$isStaff = cx_is_staff($currentUser);

$svc = new ListingService($base);
$item = $id > 0 ? $svc->findById($id) : null;

if ($item === null) {
    http_response_code(404);
}

if ($item !== null && !$isStaff && !cx_listing_is_public((string) ($item['status'] ?? ''))) {
    http_response_code(404);
    $item = null;
}

$card = $item !== null ? ShareCardService::build($item, $app, $format) : null;
$title = 'Instagram paylaşım kartı';

ob_start();
?>
<link rel="stylesheet" href="/assets/share-card.css?v=20260815a">

<div class="share-card-page">
  <?php if ($card === null): ?>
    <h1>Kart bulunamadı</h1>
    <p class="share-card-page__lead">İlan yok veya paylaşıma uygun değil.</p>
    <a class="btn btn-dark" href="/index.php">Ana sayfa</a>
  <?php else: ?>
    <h1>Instagram kartı</h1>
    <p class="share-card-page__lead">
      <strong><?= cx_e((string) $card['headline']) ?></strong> — PNG indirip Instagram feed veya story’de paylaşın.
      <?php if ($isStaff): ?><br><span style="color:#d4af37">Yönetici modu</span> (onay bekleyen ilanlar dahil).<?php endif; ?>
    </p>

    <div class="share-card-format">
      <a class="<?= $format === 'square' ? 'is-active' : '' ?>" href="/share-card.php?id=<?= $id ?>&format=square">Kare 1080×1080</a>
      <a class="<?= $format === 'story' ? 'is-active' : '' ?>" href="/share-card.php?id=<?= $id ?>&format=story">Story 1080×1920</a>
    </div>

    <div class="share-card-toolbar">
      <button class="btn btn-gold" type="button" id="btn-download-card">PNG indir</button>
      <button class="btn btn-dark" type="button" id="btn-copy-caption">Açıklamayı kopyala</button>
      <a class="btn btn-outline js-wa-share" href="#">WhatsApp (görsel)</a>
      <a class="btn btn-outline" href="/share.php?id=<?= $id ?>">Link paylaşımı</a>
      <?php if ($isStaff): ?>
        <a class="btn btn-outline" href="/admin/listing-edit.php?id=<?= $id ?>">Admin düzenle</a>
      <?php else: ?>
        <a class="btn btn-outline" href="/listing.php?id=<?= $id ?>">İlana dön</a>
      <?php endif; ?>
    </div>

    <div class="share-card-preview-wrap share-card-preview-wrap--<?= $format === 'story' ? 'story' : 'square' ?>" id="share-card-preview-wrap">
      <div class="share-card-preview-scaler" id="share-card-scaler">
        <?php require __DIR__ . '/views/partials/share-card-template.php'; ?>
      </div>
    </div>
    <div class="share-card-capture-host" id="share-card-capture-host" aria-hidden="true"></div>

    <div class="share-card-caption-box">
      <pre id="share-card-caption"><?= cx_e((string) $card['caption']) ?></pre>
    </div>

    <p class="share-card-hint">
      Instagram web’den doğrudan görsel yüklenmez. Telefonda: PNG indir → Instagram → Yeni gönderi/Story → Galeriden seç.
      Dış fotoğraf URL’lerinde (Unsplash vb.) indirme başarısız olursa ilana yerel fotoğraf ekleyin.
    </p>
  <?php endif; ?>
</div>

<?php if ($card !== null): ?>
<?php
$shareImageUrl = '';
try {
    $shareImageUrl = cx_listing_og_image_url_for_item($item, $app);
} catch (Throwable $e) {
    $shareImageUrl = '';
}
$waSharePayload = [
    'text' => (string) $card['caption'],
    'image' => $shareImageUrl,
    'fallback' => cx_whatsapp_share_url($item, $id, (int) $card['listing_no'], $app['url'] ?? ''),
];
?>
<script>window.__cxWaShare=<?= json_encode($waSharePayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?>;</script>
<script src="/assets/share-wa.js?v=20260815"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js" crossorigin="anonymous"></script>
<script>
(function () {
  var card = document.getElementById('ig-share-card');
  var wrap = document.getElementById('share-card-preview-wrap');
  var scaler = document.getElementById('share-card-scaler');
  if (!card || !wrap || !scaler) return;

  var cardW = parseInt(card.getAttribute('data-width') || '1080', 10);
  var cardH = parseInt(card.getAttribute('data-height') || '1080', 10);

  function fitPreview() {
    var boxW = wrap.clientWidth || 420;
    var scale = boxW / cardW;
    var scaledH = Math.round(cardH * scale);
    var offsetX = Math.max(0, Math.round((boxW - cardW * scale) / 2));
    scaler.style.width = cardW + 'px';
    scaler.style.transform = 'translateX(' + offsetX + 'px) scale(' + scale + ')';
    wrap.style.height = scaledH + 'px';
  }

  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(fitPreview).observe(wrap);
  }
  window.addEventListener('resize', fitPreview);
  fitPreview();

  var caption = document.getElementById('share-card-caption');
  document.getElementById('btn-copy-caption').addEventListener('click', function () {
    var text = caption ? caption.textContent : '';
    if (navigator.clipboard && text) {
      navigator.clipboard.writeText(text).then(function () {
        alert('Instagram açıklaması kopyalandı.');
      });
    }
  });

  document.getElementById('btn-download-card').addEventListener('click', function () {
    var btn = this;
    var captureHost = document.getElementById('share-card-capture-host');
    btn.disabled = true;
    btn.textContent = 'Hazırlanıyor…';

    function waitAssets(root) {
      var waits = [];
      if (document.fonts && document.fonts.ready) {
        waits.push(document.fonts.ready);
      }
      root.querySelectorAll('img').forEach(function (img) {
        if (img.complete) {
          return;
        }
        waits.push(new Promise(function (resolve) {
          img.onload = resolve;
          img.onerror = resolve;
        }));
      });
      return Promise.all(waits);
    }

    function renderPng(target) {
      return html2canvas(target, {
        scale: 1,
        width: cardW,
        height: cardH,
        useCORS: true,
        allowTaint: false,
        backgroundColor: '#0a0c10',
        logging: false,
        scrollX: 0,
        scrollY: 0
      });
    }

    waitAssets(card).then(function () {
      if (!captureHost) {
        return renderPng(card);
      }
      captureHost.innerHTML = '';
      var clone = card.cloneNode(true);
      clone.removeAttribute('id');
      clone.style.transform = 'none';
      captureHost.appendChild(clone);
      return waitAssets(clone).then(function () {
        return renderPng(clone);
      }).finally(function () {
        captureHost.innerHTML = '';
      });
    }).then(function (canvas) {
      var link = document.createElement('a');
      link.download = 'benimbazar-<?= (int) $card['listing_no'] ?>-<?= cx_e($format) ?>.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
    }).catch(function () {
      alert('Kart oluşturulamadı. Fotoğraf kaynağı engelliyor olabilir; yerel /uploads fotoğrafı deneyin.');
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = 'PNG indir';
    });
  });
})();
</script>
<?php endif; ?>
<?php
$content = ob_get_clean();
$layout = 'plain';
$bodyClass = 'page-share-card';
require __DIR__ . '/views/layout.php';
