<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
cx_bootstrap();

$trustTitle = 'KVKK Aydınlatma Metni';
$trustLead = '6698 sayılı Kişisel Verilerin Korunması Kanunu kapsamında bilgilendirme.';
ob_start();
?>
<p>BenimBazar platformunda kayıt, ilan, mesajlaşma ve doğrulama süreçlerinde işlenen kişisel veriler; hizmetin sunulması, güvenlik ve yasal yükümlülükler amacıyla işlenir.</p>
<p>Veri sorumlusu iletişim bilgileri yönetici panelinden doğrulandığında bu sayfada yayınlanır.</p>
<?php
$trustBody = ob_get_clean();
$title = 'KVKK';
$canonicalUrl = cx_canonical_url('/kvkk.php');
$layout = 'app';
$bodyClass = 'page-trust';
ob_start();
require __DIR__ . '/views/partials/trust-page.php';
$mainContent = ob_get_clean();
require __DIR__ . '/views/layout.php';
