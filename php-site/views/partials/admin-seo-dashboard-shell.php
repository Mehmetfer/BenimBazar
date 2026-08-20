<?php
declare(strict_types=1);
/** @var array<string,mixed>|null $user */
$user = $user ?? cx_current_user();
$siteUrl = cx_site_base_url();
?>
<div class="admin-seo-dash">
  <aside class="admin-seo-dash__sidebar" aria-label="Yönetim menüsü">
    <div class="admin-seo-dash__brand">
      <a href="/admin/" class="admin-seo-dash__brand-link">
        <?php
          $adminLogo = cx_brand_asset_path('logo_horizontal') ?: '/assets/branding/logo-horizontal.png';
        ?>
        <img src="<?= cx_e($adminLogo) ?>?v=20260816logo3" width="120" height="28" alt="" decoding="async">
        <span class="admin-seo-dash__brand-title"><span>Benim</span><span>Bazar</span></span>
      </a>
      <p class="admin-seo-dash__brand-tag">Türkiye ve KKTC'de otomobil</p>
    </div>

    <nav class="admin-seo-dash__nav">
      <div class="admin-seo-dash__nav-group">
        <div class="admin-seo-dash__nav-label">Ana Menü</div>
        <a class="admin-seo-dash__nav-item" href="/admin/"><span class="admin-seo-dash__nav-icon" aria-hidden="true">▦</span> Genel Bakış</a>
        <a class="admin-seo-dash__nav-item" href="/admin/"><span class="admin-seo-dash__nav-icon" aria-hidden="true">📋</span> İlanlar</a>
        <a class="admin-seo-dash__nav-item" href="/index.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">🏷</span> Kategoriler</a>
        <a class="admin-seo-dash__nav-item" href="/admin/settings.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">🖼</span> Medya</a>
        <a class="admin-seo-dash__nav-item" href="/iletisim.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">📄</span> Sayfalar</a>
        <a class="admin-seo-dash__nav-item" href="/admin/top-views.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">💬</span> Yorumlar</a>
        <?php if (cx_is_admin($user)): ?>
        <a class="admin-seo-dash__nav-item" href="/admin/users.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">👥</span> Kullanıcılar</a>
        <?php endif; ?>
      </div>

      <div class="admin-seo-dash__nav-group">
        <div class="admin-seo-dash__nav-label">Ayarlar</div>
        <a class="admin-seo-dash__nav-item" href="/admin/settings.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">⚙</span> Ayarlar</a>
        <a class="admin-seo-dash__nav-item is-active" href="/admin/seo-settings.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">🔍</span> SEO Ayarları</a>
        <a class="admin-seo-dash__nav-item" href="/admin/watermark-batch.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">🖼</span> Filigran</a>
        <a class="admin-seo-dash__nav-item" href="/sitemap.php" target="_blank" rel="noopener"><span class="admin-seo-dash__nav-icon" aria-hidden="true">🗺</span> Site Haritası</a>
        <a class="admin-seo-dash__nav-item" href="/robots.txt" target="_blank" rel="noopener"><span class="admin-seo-dash__nav-icon" aria-hidden="true">🤖</span> Robots.txt</a>
      </div>

      <div class="admin-seo-dash__nav-group">
        <div class="admin-seo-dash__nav-label">Raporlar</div>
        <a class="admin-seo-dash__nav-item" href="/admin/top-views.php"><span class="admin-seo-dash__nav-icon" aria-hidden="true">📊</span> SEO Raporları</a>
        <a class="admin-seo-dash__nav-item" href="https://search.google.com/search-console" target="_blank" rel="noopener"><span class="admin-seo-dash__nav-icon" aria-hidden="true">G</span> Google Index</a>
        <a class="admin-seo-dash__nav-item" href="https://analytics.google.com/" target="_blank" rel="noopener"><span class="admin-seo-dash__nav-icon" aria-hidden="true">📈</span> Analytics</a>
      </div>
    </nav>

    <div class="admin-seo-dash__help">
      <strong>Yardıma mı ihtiyacınız var?</strong>
      <p>SEO ve webmaster ayarları için destek talebi oluşturun.</p>
      <a class="admin-seo-dash__help-btn" href="/iletisim.php">Destek Talebi Oluştur</a>
    </div>
  </aside>

  <div class="admin-seo-dash__main">
