<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
cx_bootstrap();

$s = cx_seo_settings();
$org = is_array($s['organization'] ?? null) ? $s['organization'] : [];
$email = trim((string) ($org['email'] ?? ''));
$phone = trim((string) ($org['telephone'] ?? ''));
$gbp = cx_seo_google_profile_link();
$maps = cx_seo_google_maps_link();

$trustTitle = 'İletişim';
$trustLead = 'BenimBazar ile iletişim bilgileri.';
ob_start();
?>
<p>BenimBazar dijital bir platformdur. Aşağıdaki kanallar yalnızca yönetici tarafından doğrulanmış bilgiler içerir.</p>
<ul class="trust-contact">
  <?php if ($email !== ''): ?><li>E-posta: <a href="mailto:<?= cx_e($email) ?>"><?= cx_e($email) ?></a></li><?php endif; ?>
  <?php if ($phone !== ''): ?><li>Telefon: <a href="tel:<?= cx_e(preg_replace('/\s+/', '', $phone) ?? $phone) ?>"><?= cx_e($phone) ?></a></li><?php endif; ?>
  <?php if ($gbp !== ''): ?><li><a href="<?= cx_e($gbp) ?>" rel="noopener noreferrer">Google\'da bizi bulun</a></li><?php endif; ?>
  <?php if ($maps !== ''): ?><li><a href="<?= cx_e($maps) ?>" rel="noopener noreferrer">Google Maps</a></li><?php endif; ?>
</ul>
<?php if ($email === '' && $phone === '' && $gbp === ''): ?>
<p class="trust-page__note">İletişim bilgileri henüz yayınlanmadı. Superadmin: <a href="/admin/seo-settings.php">Google & SEO ayarları</a>.</p>
<?php endif; ?>
<?php
$trustBody = ob_get_clean();
$title = 'İletişim';
$metaDescription = 'BenimBazar iletişim — e-posta, telefon ve destek kanalları.';
$canonicalUrl = cx_canonical_url('/iletisim.php');
$layout = 'app';
$bodyClass = 'page-trust';
ob_start();
require __DIR__ . '/views/partials/trust-page.php';
$mainContent = ob_get_clean();
require __DIR__ . '/views/layout.php';
