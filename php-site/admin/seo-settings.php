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
        if (!empty($_POST['reset_defaults'])) {
            SeoSettingsService::reset();
            cx_flash('ok', 'SEO ayarları varsayılanlara sıfırlandı.');
        } else {
            SeoSettingsService::save($_POST);
            cx_flash('ok', 'Arama motoru & SEO ayarları kaydedildi.');
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    cx_redirect('/admin/seo-settings.php');
}

$siteBase = cx_site_base_url();
$socialNetworks = [
    'facebook' => 'Facebook',
    'instagram' => 'Instagram',
    'youtube' => 'Youtube',
    'tiktok' => 'Tiktok',
    'linkedin' => 'LinkedIn',
    'x' => 'X (Twitter)',
];

ob_start();
?>
<?php require dirname(__DIR__) . '/views/partials/admin-seo-dashboard-shell.php'; ?>

    <header class="admin-seo-dash__header">
      <div>
        <a class="admin-seo-dash__back" href="/admin/settings.php">← Ayarlara dön</a>
        <h1 class="admin-seo-dash__title">SEO Ayarları</h1>
        <p class="admin-seo-dash__subtitle">Google, Yandex, Bing ve genel SEO ayarlarını yönetin.</p>
      </div>
      <div class="admin-seo-dash__header-actions">
        <a class="admin-seo-dash__btn admin-seo-dash__btn--ghost" href="/index.php" target="_blank" rel="noopener">🌐 Siteyi Görüntüle</a>
        <button class="admin-seo-dash__btn admin-seo-dash__btn--primary" type="submit" form="admin-seo-form">💾 Ayarları Kaydet</button>
      </div>
    </header>

    <form method="post" class="admin-seo-dash__form" id="admin-seo-form">
      <?= cx_csrf_field() ?>

      <div class="admin-seo-dash__grid">
        <div class="admin-seo-dash__col admin-seo-dash__col--left">
          <section class="admin-seo-card">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--green" aria-hidden="true">🔍</span>
              <h2 class="admin-seo-card__title">Ana Sayfa SEO</h2>
            </header>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Varsayılan Title</span>
              <input class="admin-seo-field__input" type="text" name="default_title" value="<?= cx_e((string) ($s['default_title'] ?? '')) ?>" maxlength="120">
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Meta Description</span>
              <textarea class="admin-seo-field__textarea" name="default_description" rows="3" maxlength="320"><?= cx_e((string) ($s['default_description'] ?? '')) ?></textarea>
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Site İçi Arama URL Şablonu</span>
              <input class="admin-seo-field__input" type="text" name="search_url_template" value="<?= cx_e((string) ($s['search_url_template'] ?? '')) ?>" placeholder="/index.php?q={search_term_string}">
            </label>
          </section>

          <section class="admin-seo-card">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--google" aria-hidden="true">G</span>
              <h2 class="admin-seo-card__title">Google Search Console</h2>
            </header>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Site Doğrulama Meta (content)</span>
              <input class="admin-seo-field__input" type="text" name="google_site_verification" value="<?= cx_e((string) ($s['google_site_verification'] ?? '')) ?>" placeholder="google-site-verification token">
            </label>
          </section>

          <section class="admin-seo-card">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--maps" aria-hidden="true">🏪</span>
              <h2 class="admin-seo-card__title">Google Business Profile</h2>
            </header>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Profil URL</span>
              <input class="admin-seo-field__input" type="url" name="google_business_profile_url" value="<?= cx_e((string) ($s['google_business_profile_url'] ?? '')) ?>" placeholder="https://...">
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Google Maps URL</span>
              <input class="admin-seo-field__input" type="url" name="google_maps_url" value="<?= cx_e((string) ($s['google_maps_url'] ?? '')) ?>" placeholder="https://maps.google.com/...">
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Place ID</span>
              <input class="admin-seo-field__input" type="text" name="google_place_id" value="<?= cx_e((string) ($s['google_place_id'] ?? '')) ?>">
            </label>
          </section>
        </div>

        <div class="admin-seo-dash__col admin-seo-dash__col--center">
          <section class="admin-seo-card">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--yandex" aria-hidden="true">Y</span>
              <h2 class="admin-seo-card__title">Yandex Webmaster</h2>
            </header>
            <p class="admin-seo-card__hint">Doğrulama sonrası aynı sitemap URL'lerini Yandex'e ekleyin: <code>/sitemap.php</code>, <code>/sitemap-listings.php</code></p>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Yandex Doğrulama Meta (content)</span>
              <input class="admin-seo-field__input" type="text" name="yandex_site_verification" value="<?= cx_e((string) ($s['yandex_site_verification'] ?? '')) ?>" placeholder="yandex-verification token">
            </label>
          </section>

          <section class="admin-seo-card">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--bing" aria-hidden="true">b</span>
              <h2 class="admin-seo-card__title">Yahoo / Bing Webmaster</h2>
            </header>
            <p class="admin-seo-card__hint">Yahoo arama sonuçları Bing altyapısını kullanır. Doğrulama <a href="https://www.bing.com/webmasters" target="_blank" rel="noopener">Bing Webmaster Tools</a> üzerinden yapılır.</p>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Bing Doğrulama Meta (content)</span>
              <input class="admin-seo-field__input" type="text" name="bing_site_verification" value="<?= cx_e((string) ($s['bing_site_verification'] ?? '')) ?>" placeholder="msvalidate.01 token">
            </label>
          </section>

          <section class="admin-seo-card">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--social" aria-hidden="true">🔗</span>
              <h2 class="admin-seo-card__title">Sosyal Medya (sameAs)</h2>
            </header>
            <p class="admin-seo-card__hint">Yalnızca gerçek hesaplar</p>
            <div class="admin-seo-field-grid">
              <?php foreach ($socialNetworks as $net => $label): ?>
              <label class="admin-seo-field">
                <span class="admin-seo-field__label"><?= cx_e($label) ?></span>
                <input class="admin-seo-field__input" type="url" name="social_<?= cx_e($net) ?>" value="<?= cx_e((string) ($social[$net] ?? '')) ?>" placeholder="https://...">
              </label>
              <?php endforeach; ?>
            </div>
          </section>
        </div>

        <div class="admin-seo-dash__col admin-seo-dash__col--right">
          <section class="admin-seo-card admin-seo-card--tall">
            <header class="admin-seo-card__head">
              <span class="admin-seo-card__icon admin-seo-card__icon--org" aria-hidden="true">🏢</span>
              <h2 class="admin-seo-card__title">Marka / İşletme (Organization Schema)</h2>
            </header>
            <p class="admin-seo-card__hint">Yalnızca dolu alanlar kullanılır.</p>

            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Resmi Ad</span>
              <input class="admin-seo-field__input" type="text" name="org_legal_name" value="<?= cx_e((string) ($org['legal_name'] ?? '')) ?>">
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Açıklama</span>
              <textarea class="admin-seo-field__textarea" name="org_description" rows="2"><?= cx_e((string) ($org['description'] ?? '')) ?></textarea>
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">E-posta</span>
              <input class="admin-seo-field__input" type="email" name="org_email" value="<?= cx_e((string) ($org['email'] ?? '')) ?>" placeholder="info@benimbazar.com">
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Telefon</span>
              <input class="admin-seo-field__input" type="text" name="org_telephone" value="<?= cx_e((string) ($org['telephone'] ?? '')) ?>" placeholder="+90 5XX XXX XX XX">
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Adres</span>
              <input class="admin-seo-field__input" type="text" name="org_address_street" value="<?= cx_e((string) ($org['address_street'] ?? '')) ?>">
            </label>

            <div class="admin-seo-field-row">
              <label class="admin-seo-field">
                <span class="admin-seo-field__label">Şehir</span>
                <input class="admin-seo-field__input" type="text" name="org_address_city" value="<?= cx_e((string) ($org['address_city'] ?? '')) ?>" placeholder="Lefkoşa">
              </label>
              <label class="admin-seo-field">
                <span class="admin-seo-field__label">Bölge</span>
                <input class="admin-seo-field__input" type="text" name="org_address_region" value="<?= cx_e((string) ($org['address_region'] ?? '')) ?>" placeholder="-">
              </label>
            </div>

            <div class="admin-seo-field-row">
              <label class="admin-seo-field">
                <span class="admin-seo-field__label">Posta Kodu</span>
                <input class="admin-seo-field__input" type="text" name="org_address_postal" value="<?= cx_e((string) ($org['address_postal'] ?? '')) ?>">
              </label>
              <label class="admin-seo-field">
                <span class="admin-seo-field__label">Ülke (TR / CY)</span>
                <?php $country = strtoupper(trim((string) ($org['address_country'] ?? ''))); ?>
                <select class="admin-seo-field__input admin-seo-field__select" name="org_address_country">
                  <option value=""<?= $country === '' ? ' selected' : '' ?>>Seçin</option>
                  <option value="TR"<?= $country === 'TR' ? ' selected' : '' ?>>TR</option>
                  <option value="CY"<?= $country === 'CY' ? ' selected' : '' ?>>CY</option>
                </select>
              </label>
            </div>

            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Hizmet Bölgeleri</span>
              <textarea class="admin-seo-field__textarea" name="org_service_areas" rows="2" placeholder="Türkiye, KKTC"><?= cx_e((string) ($org['service_areas'] ?? '')) ?></textarea>
            </label>
            <label class="admin-seo-field">
              <span class="admin-seo-field__label">Çalışma Saatleri</span>
              <input class="admin-seo-field__input" type="text" name="org_opening_hours" value="<?= cx_e((string) ($org['opening_hours'] ?? '')) ?>" placeholder="09:00 - 18:00 (Pzt - Cmt)">
            </label>
          </section>
        </div>
      </div>

      <div class="admin-seo-dash__info" role="note">
        <strong>Bilgilendirme</strong>
        <p>Bu ayarlar Google Business Profile, Search Console, Yandex/Bing doğrulama meta etiketleri ve Organization Schema için kullanılır. Boş bırakılan alanlar sitede <strong>gösterilmez</strong> — sahte bilgi üretilmez.</p>
      </div>

      <footer class="admin-seo-dash__footer">
        <div class="admin-seo-dash__footer-links">
          Canonical taban: <code><?= cx_e($siteBase) ?></code> ·
          Sitemap: <a href="/sitemap.php" target="_blank" rel="noopener">/sitemap.php</a> ·
          <a href="/sitemap-listings.php" target="_blank" rel="noopener">/sitemap-listings.php</a> ·
          <a href="/robots.txt" target="_blank" rel="noopener">/robots.txt</a>
          · Webmaster:
          <a href="https://search.google.com/search-console" target="_blank" rel="noopener">Google</a> ·
          <a href="https://webmaster.yandex.com/" target="_blank" rel="noopener">Yandex</a> ·
          <a href="https://www.bing.com/webmasters" target="_blank" rel="noopener">Bing/Yahoo</a>
        </div>
        <div class="admin-seo-dash__footer-actions">
          <button class="admin-seo-dash__btn admin-seo-dash__btn--ghost" type="submit" name="reset_defaults" value="1" formnovalidate onclick="return confirm('Tüm SEO ayarları varsayılanlara sıfırlansın mı?');">↺ Sıfırla</button>
          <button class="admin-seo-dash__btn admin-seo-dash__btn--primary admin-seo-dash__btn--lg" type="submit">💾 Ayarları Kaydet</button>
        </div>
      </footer>
    </form>

  </div>
</div>

<?php
$content = ob_get_clean();
$title = 'SEO Ayarları';
$layout = 'admin';
$bodyClass = 'page-admin page-admin-seo';
$adminTab = 'seo';
require dirname(__DIR__) . '/views/layout.php';
