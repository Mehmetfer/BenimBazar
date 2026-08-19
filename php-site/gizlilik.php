<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
cx_bootstrap();

$trustTitle = 'Gizlilik Politikası';
$trustLead = 'Kişisel verilerinizin korunmasına ilişkin genel bilgilendirme.';
ob_start();
?>
<p>BenimBazar, kullanıcı hesapları, ilan içerikleri ve mesajlaşma verilerini hizmet sunumu için işler. Detaylı metin yönetici tarafından güncellenecektir.</p>
<p>KVKK kapsamındaki haklarınız için <a href="/kvkk.php">KVKK Aydınlatma Metni</a> sayfasına bakın.</p>
<?php
$trustBody = ob_get_clean();
$title = 'Gizlilik Politikası';
$canonicalUrl = cx_canonical_url('/gizlilik.php');
$layout = 'app';
$bodyClass = 'page-trust';
ob_start();
require __DIR__ . '/views/partials/trust-page.php';
$mainContent = ob_get_clean();
require __DIR__ . '/views/layout.php';
