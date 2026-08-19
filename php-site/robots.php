<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

cx_bootstrap();

header('Content-Type: text/plain; charset=UTF-8');
header('X-Robots-Tag: noindex', true);
echo cx_seo_robots_txt_body();
