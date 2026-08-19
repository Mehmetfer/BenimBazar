<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
cx_bootstrap();

$trustTitle = 'Sık Sorulan Sorular';
$trustLead = 'BenimBazar hakkında sık sorulan sorular.';
$trustFaq = [
    ['q' => 'BenimBazar nedir?', 'a' => 'Türkiye ve KKTC odaklı dijital araç ve ilan pazaryeridir. Bireysel ve kurumsal satıcılar araç ilanı yayınlayabilir.'],
    ['q' => 'Nasıl ilan verilir?', 'a' => 'Giriş yaptıktan sonra "İlan ver" adımlarını izleyerek fotoğraf, araç bilgileri ve fiyat/takas tercihinizi girin. İlan moderasyon sonrası yayına alınır.'],
    ['q' => 'Galeriler ilan yayınlayabilir mi?', 'a' => 'Evet. Kurumsal ve VIP Kurumsal galeri hesapları mağaza vitrinleri ve ilanları ile listelenir.'],
    ['q' => 'Araç takası nasıl yapılır?', 'a' => 'İlan oluştururken takas modunu seçebilir ve karşılık beklentinizi yazabilirsiniz.'],
    ['q' => 'İlan nasıl kaldırılır?', 'a' => 'İlan sahibi "İlanlarım" üzerinden düzenleyebilir veya satıldı olarak işaretleyebilir.'],
];
$trustBody = '';
$title = 'SSS';
$metaDescription = 'BenimBazar sık sorulan sorular — ilan verme, galeriler, takas ve moderasyon.';
$canonicalUrl = cx_canonical_url('/sss.php');
$faqSchema = [
    '@context' => 'https://schema.org',
    '@type' => 'FAQPage',
    'mainEntity' => array_map(static fn (array $row): array => [
        '@type' => 'Question',
        'name' => $row['q'],
        'acceptedAnswer' => ['@type' => 'Answer', 'text' => $row['a']],
    ], $trustFaq),
];
$jsonLd = json_encode($faqSchema, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?: '';
$layout = 'app';
$bodyClass = 'page-trust';
ob_start();
require __DIR__ . '/views/partials/trust-page.php';
$mainContent = ob_get_clean();
require __DIR__ . '/views/layout.php';
