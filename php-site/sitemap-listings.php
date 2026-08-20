<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingService.php';

use App\Services\ListingService;

cx_bootstrap();

header('Content-Type: application/xml; charset=UTF-8');

$base = cx_site_base_url();
$page = max(1, (int) ($_GET['page'] ?? 1));
$perPage = 500;
$offset = ($page - 1) * $perPage;

$pdo = \App\Helpers\Database::pdo();
$stmt = $pdo->prepare(
    "SELECT id, updated_at FROM trade_listings
     WHERE UPPER(COALESCE(status,'')) IN ('APPROVED','ACTIVE')
     ORDER BY id DESC
     LIMIT " . (int) $perPage . " OFFSET " . (int) $offset
);
$stmt->execute();
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];

echo '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";
foreach ($rows as $row) {
    $id = (int) ($row['id'] ?? 0);
    if ($id <= 0) {
        continue;
    }
    $loc = $base . '/listing.php?id=' . $id;
    $updated = (float) ($row['updated_at'] ?? 0);
    echo '  <url><loc>' . htmlspecialchars($loc, ENT_XML1) . '</loc>';
    if ($updated > 0) {
        echo '<lastmod>' . gmdate('c', (int) $updated) . '</lastmod>';
    }
    echo '</url>' . "\n";
}
echo '</urlset>';
