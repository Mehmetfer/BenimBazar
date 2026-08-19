<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SocialService.php';
require_once __DIR__ . '/app/Services/ListingService.php';

use App\Services\ListingService;
use App\Services\MarketCompareService;

cx_bootstrap();

$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$id = (int) ($_GET['id'] ?? 0);
if ($id <= 0) {
    cx_redirect('/index.php');
}

$user = cx_current_user();
$svc = new ListingService($base);
$item = $svc->findById($id, $user ? (int) $user['id'] : null);

if ($item === null || !cx_can_view_listing($user, $item)) {
    http_response_code(404);
    $metaRobots = cx_seo_robots_noindex();
    $title = 'İlan bulunamadı';
    $metaDescription = 'Aradığınız ilan yayından kaldırılmış veya mevcut değil.';
    $layout = 'app';
    $bodyClass = 'page-not-found';
    ob_start();
    echo '<section class="not-found"><h1>Aradığınız ilan bulunamadı</h1><p>Bu ilan silinmiş, satılmış veya moderasyon nedeniyle görüntülenemiyor olabilir.</p><p><a class="btn" href="/">Ana sayfaya dön</a> · <a href="/index.php?veh=otomobil">Araç ilanları</a></p></section>';
    $mainContent = ob_get_clean();
    require __DIR__ . '/views/layout.php';
    exit;
}

try {
    if ((new \App\Services\ListingViewService())->record($id, $user)) {
        $item['view_count'] = (int) ($item['view_count'] ?? 0) + 1;
    }
} catch (Throwable) {
    // goruntulenme sayaci opsiyonel
}

$photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]', $app['uploads_url'] ?? '/uploads');
$no = cx_listing_no_display($item, $base);
$share = cx_share_url($no, $app['url'] ?? '');
$whatsappShare = cx_whatsapp_share_url($item, $id, $no, $app['url'] ?? '');
$whatsappShareText = cx_whatsapp_share_text($item, $id, $no, $app['url'] ?? '');
$shareImageUrl = cx_listing_og_image_url($id, (string) ($app['url'] ?? ''));
$ogMeta = null;
try {
    $ogMeta = cx_listing_open_graph($item, $id, $no, $app, $shareImageUrl);
} catch (Throwable $e) {
    // Paylasim karti olmadan ilan sayfasi acilir
}
$waSharePayload = [
    'text' => $whatsappShareText,
    'image' => $shareImageUrl,
    'fallback' => $whatsappShare,
];
$ownerId = (int) ($item['owner_id'] ?? 0);

$similarItems = $svc->findSimilarPublic($item, $user ? (int) $user['id'] : null);
$similarAttrs = cx_listing_attrs($item);
$similarAttrs['_title'] = (string) ($item['title'] ?? '');
$similarContext = cx_listing_similar_context_label($similarAttrs);

$marketCompare = null;
try {
    $marketCompare = (new MarketCompareService())->analyze($item);
} catch (Throwable) {
    $marketCompare = null;
}

$priceHistorySummary = ['points' => []];
try {
    $priceHistorySummary = cx_price_history_summarize(
        (new \App\Services\PriceHistoryService())->forListing($id)
    );
} catch (Throwable) {
    $priceHistorySummary = ['points' => []];
}

ob_start();
require __DIR__ . '/views/partials/listing-detail.php';
$mainContent = ob_get_clean();

$listingSeo = cx_listing_seo_meta($item, $id, $no);
$title = $listingSeo['title'];
$titleStandalone = true;
$metaDescription = $listingSeo['description'];
$canonicalUrl = $listingSeo['canonical'];
$jsonLd = $listingSeo['json_ld'];
$listingBreadcrumbs = $listingSeo['breadcrumbs'];
$layout = 'app';
$navActive = 'home';
$bodyClass = 'page-listing-detail';
require __DIR__ . '/views/layout.php';
