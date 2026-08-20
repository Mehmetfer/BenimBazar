<?php



declare(strict_types=1);



require __DIR__ . '/bootstrap.php';

require_once __DIR__ . '/app/Services/ListingService.php';



use App\Services\ListingService;



cx_bootstrap();



$app = cx_app_config();

$base = (int) ($app['listing_no_base'] ?? 1000000000);

$id = (int) ($_GET['id'] ?? 0);

$svc = new ListingService($base);

$item = $id > 0 ? $svc->findById($id) : null;



if ($item === null || !cx_listing_is_public((string) ($item['status'] ?? ''))) {

    http_response_code(404);

    $item = null;

}



$no = $item ? (int) ($item['listing_no'] ?? cx_listing_no($id, $base)) : 0;

$url = $item ? cx_listing_share_url($id, $app['url'] ?? '') : '';

$whatsappShare = $item ? cx_whatsapp_share_url($item, $id, $no, $app['url'] ?? '') : '';

$shareImageUrl = $item ? cx_listing_og_image_url_for_item($item, $app) : '';

$whatsappShareText = $item ? cx_whatsapp_share_text($item, $id, $no, $app['url'] ?? '') : '';

$waSharePayload = $item ? [

    'text' => $whatsappShareText,

    'image' => $shareImageUrl,

    'fallback' => $whatsappShare,

] : [];



ob_start();

if (!$item) {

    echo '<p class="muted">İlan bulunamadı.</p>';

} else {

    ?>

    <h1>Paylaş</h1>

    <p><strong><?= cx_e($item['title']) ?></strong></p>

    <p class="ilan-no">İlan No: <?= $no ?></p>

    <?php if ($shareImageUrl !== ''): ?>

    <img src="<?= cx_e($shareImageUrl) ?>" alt="Paylaşım kartı" style="max-width:100%;border-radius:12px;margin:.75rem 0;border:1px solid #2a3140">

    <?php endif; ?>

    <div class="share-box" id="share-url"><?= cx_e($url) ?></div>

    <p class="muted">Telefonda <strong>WhatsApp (görsel)</strong> ile kart fotoğrafı + metin birlikte gider. Masaüstünde metin + link açılır.</p>

    <p class="muted">Link önizlemesinde büyük görsel için sitede SSL (https) gerekir — Natro/cPanel AutoSSL ile changex alt alan adına sertifika ekleyin.</p>

    <div class="actions">

      <button class="btn btn-gold" type="button" onclick="navigator.clipboard.writeText(document.getElementById('share-url').innerText);alert('Link kopyalandı')">Link kopyala</button>

      <a class="btn btn-gold" href="/share-card.php?id=<?= $id ?>">Instagram kartı</a>

      <a class="btn btn-gold js-wa-share" href="#">WhatsApp (görsel + link)</a>

      <a class="btn" target="_blank" rel="noopener" href="<?= cx_e($whatsappShare) ?>">WhatsApp (sadece metin)</a>

      <a class="btn" href="/listing.php?id=<?= $id ?>">İlana dön</a>

    </div>

    <script>window.__cxWaShare=<?= json_encode($waSharePayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?>;</script>

    <script src="/assets/share-wa.js?v=20260815"></script>

    <?php

}

$content = ob_get_clean();

$title = 'Paylaş';

require __DIR__ . '/views/layout.php';

