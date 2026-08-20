<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

cx_bootstrap();
cx_redirect('/index.php?' . http_build_query(array_filter([
    '__seo_path' => trim((string) ($_GET['path'] ?? ''), '/'),
], static fn ($v) => $v !== '')));
