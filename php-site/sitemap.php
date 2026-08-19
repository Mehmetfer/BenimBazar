<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

cx_bootstrap();

header('Content-Type: application/xml; charset=UTF-8');

$base = cx_site_base_url();
$paths = cx_seo_sitemap_paths();

$static = [
    '/hakkimizda.php',
    '/iletisim.php',
    '/sss.php',
    '/gizlilik.php',
    '/kvkk.php',
    '/kullanim-kosullari.php',
    '/ekspertiz-kosullari.php',
];

echo '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";

$seen = [];
$emit = static function (string $loc) use (&$seen): void {
    if (isset($seen[$loc])) {
        return;
    }
    $seen[$loc] = true;
    echo '  <url><loc>' . htmlspecialchars($loc, ENT_XML1) . '</loc></url>' . "\n";
};

$emit($base . '/');
foreach ($paths as $path) {
    if ($path === '/') {
        continue;
    }
    $emit($base . $path);
}
if (cx_gallery_discovery_enabled()) {
    $emit($base . '/galeriler');
}
foreach ($static as $path) {
    $emit($base . $path);
}

echo '</urlset>';
