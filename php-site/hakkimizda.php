<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
cx_bootstrap();

$trustTitle = 'Hakkımızda';
$trustLead = 'BenimBazar, Türkiye ve KKTC odaklı dijital araç ve ilan pazaryeridir.';
ob_start();
?>
<p>BenimBazar ile otomobil, motosiklet, bisiklet, ticari ve antika araç ilanlarını keşfedebilir; satılık ilan verebilir veya takas seçeneklerini değerlendirebilirsiniz.</p>
<p>Kurumsal galeriler ve VIP mağazalar vitrinlerini BenimBazar üzerinden yönetir; alıcılar ilan detayları, mesajlaşma ve galeri sayfaları üzerinden satıcılarla iletişime geçebilir.</p>
<p>Platform dijital bir pazaryeridir. İletişim ve adres bilgileri yalnızca doğrulanmış kaynaklardan yayınlanır.</p>
<?php
$trustBody = ob_get_clean();
$title = 'Hakkımızda';
$metaDescription = 'BenimBazar nedir? Türkiye ve KKTC\'de araç ilanları, galeriler ve takas pazaryeri hakkında bilgi.';
$canonicalUrl = cx_canonical_url('/hakkimizda.php');
$layout = 'app';
$bodyClass = 'page-trust';
ob_start();
require __DIR__ . '/views/partials/trust-page.php';
$mainContent = ob_get_clean();
require __DIR__ . '/views/layout.php';
