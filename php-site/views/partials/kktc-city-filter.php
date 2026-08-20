<?php

declare(strict_types=1);

/** @var string $region */

/** @var string $kktcCity */

/** @var string $veh */

/** @var string $q */

/** @var string $cat */

/** @var string $subcat */



require_once __DIR__ . '/../../app/Helpers/kktc-locations.php';



$region = $region ?? cx_region_from_request(null);

if ($region !== 'kktc') {

    return;

}

$kktcCity = $kktcCity ?? cx_kktc_city_from_request();

$veh = $veh ?? trim((string) ($_GET['veh'] ?? ''));

$q = $q ?? trim((string) ($_GET['q'] ?? ''));

$cat = $cat ?? 'TÜM TAKASLAR';

$subcat = $subcat ?? '';



$make = '';

if ($veh !== '' && !empty($_GET['make']) && is_array($_GET['make']) && ($_GET['make'][0] ?? '') !== '') {

    $make = (string) $_GET['make'][0];

}



if (cx_seo_landing_enabled()) {

    $allHref = cx_seo_kktc_city_href('', $veh, $make);

} else {

    $baseParams = cx_region_query_params();

    unset($baseParams['city']);

    $allHref = '/index.php?' . http_build_query(array_merge($baseParams, array_filter([

        'veh' => $veh !== '' ? $veh : null,

        'q' => $q !== '' ? $q : null,

        'subcat' => ($veh === '' && $subcat !== '') ? $subcat : null,

        'cat' => ($veh === '' && $subcat === '' && $cat !== 'TÜM TAKASLAR' && !cx_meta_category($cat)) ? $cat : null,

    ], static fn ($v) => $v !== null && $v !== '')), '', '&', PHP_QUERY_RFC3986);

}

?>

<nav class="kktc-city-filter" aria-label="KKTC şehir filtresi">

  <a class="kktc-city-filter__chip<?= $kktcCity === '' ? ' is-active' : '' ?>" href="<?= cx_e($allHref) ?>">Tüm KKTC</a>

  <?php foreach (cx_kktc_cities() as $code => $row): ?>

    <?php

      $chipHref = cx_seo_landing_enabled()

          ? cx_seo_kktc_city_href($code, $veh, $make)

          : '/index.php?' . http_build_query(array_merge(cx_region_query_params(), ['city' => $code], array_filter([

              'veh' => $veh !== '' ? $veh : null,

              'q' => $q !== '' ? $q : null,

              'subcat' => ($veh === '' && $subcat !== '') ? $subcat : null,

              'cat' => ($veh === '' && $subcat === '' && $cat !== 'TÜM TAKASLAR' && !cx_meta_category($cat)) ? $cat : null,

          ], static fn ($v) => $v !== null && $v !== '')), '', '&', PHP_QUERY_RFC3986);

    ?>

    <a class="kktc-city-filter__chip<?= $kktcCity === $code ? ' is-active' : '' ?>" href="<?= cx_e($chipHref) ?>"><?= cx_e($row['label']) ?></a>

  <?php endforeach; ?>

</nav>

