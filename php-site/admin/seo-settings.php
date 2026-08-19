<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/SeoSettingsService.php';

use App\Helpers\Security;
use App\Services\SeoSettingsService;

cx_bootstrap();
$user = cx_require_user();

if (!cx_is_superadmin($user)) {
    cx_flash('error', 'Google & SEO ayarları yalnızca superadmin içindir.');
    cx_redirect('/admin/');
}

$s = SeoSettingsService::read();
$org = is_array($s['organization'] ?? null) ? $s['organization'] : [];
$social = is_array($s['social'] ?? null) ? $s['social'] : [];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    Security::rateLimit('admin_seo_settings', 20, 300);
    try {
        SeoSettingsService::save($_POST);
        cx_flash('ok', 'Arama motoru & SEO ayarları kaydedildi.');
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    cx_redirect('/admin/seo-settings.php');
}

ob_start();
$adminTab = 'seo';
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<p class="admin-list-meta">
  Google Business Profile, Search Console ve site geneli SEO ayarları.
  Boş bırakılan alanlar Schema veya sitede <strong>gösterilmez</strong> (sahte bilgi üretilmez).
</p>

<form method="post" class="admin-seo-form">
  <?= cx_csrf_field() ?>

  <fieldset class="admin-seo-form__block">
    <legend>Ana sayfa SEO</legend>
    <label>Varsayılan title<input type="text" name="default_title" value="<?= cx_e((string) ($s['default_title'] ?? '')) ?>" maxlength="120"></label>
    <label>Meta description<textarea name="default_description" rows="3" maxlength="320"><?= cx_e((string) ($s['default_description'] ?? '')) ?></textarea></label>
    <label>Site içi arama URL şablonu<input type="text" name="search_url_template" value="<?= cx_e((string) ($s['search_url_template'] ?? '')) ?>" placeholder="/index.php?q={search_term_string}"></label>
  </fieldset>

  <fieldset class="admin-seo-form__block">
    <legend>Yandex Webmaster</legend>
    <p class="admin-seo-form__hint">Doğrulama sonrası aynı sitemap URL'lerini Yandex'e ekleyin: <code>/sitemap.php</code>, <code>/sitemap-listings.php</code></p>
    <label>Yandex doğrulama meta (content)<input type="text" name="yandex_site_verification" value="<?= cx_e((string) ($s['yandex_site_verification'] ?? '')) ?>" placeholder="yandex-verification token"></label>
  </fieldset>

  <fieldset class="admin-seo-form__block">
    <legend>Yahoo / Bing Webmaster</legend>
    <p class="admin-seo-form__hint">Yahoo arama sonuçları Bing altyapısını kullanır. Doğrulama <a class="link-gold" href="https://www.bing.com/webmasters" target="_blank" rel="noopener">Bing Webmaster Tools</a> üzerinden yapılır.</p>
    <label>Bing doğrulama meta — msvalidate.01 (content)<input type="text" name="bing_site_verification" value="<?= cx_e((string) ($s['bing_site_verification'] ?? '')) ?>" placeholder="msvalidate.01 token"></label>
  </fieldset>

  <fieldset class="admin-seo-form__block">
    <legend>Google Search Console</legend>
    <label>Site doğrulama meta (content)<input type="text" name="google_site_verification" value="<?= cx_e((string) ($s['google_site_verification'] ?? '')) ?>" placeholder="google-site-verification token"></label>
  </fieldset>

  <fieldset class="admin-seo-form__block">
    <legend>Google Business Profile (profil oluşturulduktan sonra)</legend>
    <label>Profil URL<input type="url" name="google_business_profile_url" value="<?= cx_e((string) ($s['google_business_profile_url'] ?? '')) ?>" placeholder="https://..."></label>
    <label>Google Maps URL<input type="url" name="google_maps_url" value="<?= cx_e((string) ($s['google_maps_url'] ?? '')) ?>" placeholder="https://maps.google.com/..."></label>
    <label>Place ID<input type="text" name="google_place_id" value="<?= cx_e((string) ($s['google_place_id'] ?? '')) ?>"></label>
  </fieldset>

  <fieldset class="admin-seo-form__block">
    <legend>Marka / işletme (Organization Schema — yalnızca dolu alanlar kullanılır)</legend>
    <label>Resmi ad<input type="text" name="org_legal_name" value="<?= cx_e((string) ($org['legal_name'] ?? '')) ?>"></label>
    <label>Açıklama<textarea name="org_description" rows="2"><?= cx_e((string) ($org['description'] ?? '')) ?></textarea></label>
    <label>E-posta<input type="email" name="org_email" value="<?= cx_e((string) ($org['email'] ?? '')) ?>"></label>
    <label>Telefon<input type="text" name="org_telephone" value="<?= cx_e((string) ($org['telephone'] ?? '')) ?>"></label>
    <label>Adres<input type="text" name="org_address_street" value="<?= cx_e((string) ($org['address_street'] ?? '')) ?>"></label>
    <label>Şehir<input type="text" name="org_address_city" value="<?= cx_e((string) ($org['address_city'] ?? '')) ?>"></label>
    <label>Bölge<input type="text" name="org_address_region" value="<?= cx_e((string) ($org['address_region'] ?? '')) ?>"></label>
    <label>Posta kodu<input type="text" name="org_address_postal" value="<?= cx_e((string) ($org['address_postal'] ?? '')) ?>"></label>
    <label>Ülke (TR / CY)<input type="text" name="org_address_country" value="<?= cx_e((string) ($org['address_country'] ?? '')) ?>"></label>
    <label>Hizmet bölgeleri<textarea name="org_service_areas" rows="2" placeholder="Türkiye, KKTC"><?= cx_e((string) ($org['service_areas'] ?? '')) ?></textarea></label>
    <label>Çalışma saatleri<textarea name="org_opening_hours" rows="2"><?= cx_e((string) ($org['opening_hours'] ?? '')) ?></textarea></label>
  </fieldset>

  <fieldset class="admin-seo-form__block">
    <legend>Sosyal medya (sameAs — yalnızca gerçek hesaplar)</legend>
    <?php foreach (['facebook', 'instagram', 'youtube', 'tiktok', 'linkedin', 'x'] as $net): ?>
    <label><?= cx_e(ucfirst($net)) ?><input type="url" name="social_<?= cx_e($net) ?>" value="<?= cx_e((string) ($social[$net] ?? '')) ?>"></label>
    <?php endforeach; ?>
  </fieldset>

  <button class="admin-btn" type="submit">Kaydet</button>
</form>

<p class="admin-list-meta">
  Canonical taban: <code><?= cx_e(cx_site_base_url()) ?></code> ·
  Sitemap: <a class="link-gold" href="/sitemap.php" target="_blank" rel="noopener">/sitemap.php</a> ·
  <a class="link-gold" href="/sitemap-listings.php" target="_blank" rel="noopener">/sitemap-listings.php</a> ·
  <a class="link-gold" href="/robots.txt" target="_blank" rel="noopener">/robots.txt</a>
</p>
<p class="admin-list-meta admin-seo-form__hint">
  Webmaster: <a class="link-gold" href="https://search.google.com/search-console" target="_blank" rel="noopener">Google</a> ·
  <a class="link-gold" href="https://webmaster.yandex.com/" target="_blank" rel="noopener">Yandex</a> ·
  <a class="link-gold" href="https://www.bing.com/webmasters" target="_blank" rel="noopener">Bing/Yahoo</a>
</p>

<?php
$content = ob_get_clean();
$title = 'Arama Motorları & SEO';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
