<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SocialService.php';
require_once __DIR__ . '/app/Services/ListingService.php';

use App\Services\ListingService;

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
    cx_flash('error', 'İlan bulunamadı.');
    cx_redirect('/index.php');
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

ob_start();
require __DIR__ . '/views/partials/listing-detail.php';
$mainContent = ob_get_clean();

$title = (string) $item['title'];
$layout = 'app';
$navActive = 'home';
$bodyClass = 'page-listing-detail';
require __DIR__ . '/views/layout.php';
