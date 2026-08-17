<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingWriteService.php';

use App\Helpers\Security;
use App\Services\ListingWriteService;

cx_bootstrap();
$user = cx_require_user();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    cx_redirect('/my-listings.php');
}

Security::requireCsrf();
Security::rateLimit('listing_action', 40, 300);

$action = (string) ($_POST['action'] ?? '');
$listingId = (int) ($_POST['listing_id'] ?? 0);
$back = cx_safe_next((string) ($_POST['back'] ?? '/my-listings.php'));
$writer = new ListingWriteService();

try {
    if ($listingId <= 0) {
        throw new RuntimeException('Gecersiz ilan.');
    }
    if ($action === 'mark_sold') {
        $writer->markSold($listingId, (int) $user['id']);
        cx_flash('ok', 'Ilan satildi olarak isaretlendi.');
    } elseif ($action === 'republish') {
        $writer->republish($listingId, (int) $user['id']);
        cx_flash('ok', 'Ilan yeniden moderasyona gonderildi.');
    } else {
        throw new RuntimeException('Gecersiz islem.');
    }
} catch (Throwable $e) {
    cx_flash('error', $e->getMessage());
}

cx_redirect($back);
