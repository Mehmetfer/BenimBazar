<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

use App\Helpers\Auth;
use App\Helpers\Database;
use App\Helpers\Security;
use App\Services\ListingSchemaService;

cx_bootstrap();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::rateLimit('register', 15, 3600);
    Security::requireCsrf();

    $username = trim((string) ($_POST['username'] ?? ''));
    $password = (string) ($_POST['password'] ?? '');
    $password2 = (string) ($_POST['password2'] ?? '');
    $email = trim((string) ($_POST['email'] ?? ''));
    $phone = trim((string) ($_POST['phone'] ?? ''));
    $city = trim((string) ($_POST['city'] ?? ''));
    $country = cx_normalize_country((string) ($_POST['country'] ?? ''));

    $errors = [];
    if ($username === '' || strlen($username) < 3) {
        $errors[] = 'Kullanici adi en az 3 karakter olmali.';
    }
    if (strlen($password) < 6) {
        $errors[] = 'Sifre en az 6 karakter olmali.';
    }
    if ($password !== $password2) {
        $errors[] = 'Sifre tekrari eslesmiyor.';
    }
    if ($email === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $errors[] = 'Gecerli bir e-posta girin.';
    }
    $phoneDigits = preg_replace('/\D+/', '', $phone) ?? '';
    if ($phoneDigits === '' || strlen($phoneDigits) < 10) {
        $errors[] = 'Gecerli bir GSM numarasi girin (orn. 0533 123 45 67).';
    }
    if ($city === '') {
        $errors[] = 'Konum / sehir zorunlu.';
    }
    if (!in_array($country, ['kktc', 'tr'], true)) {
        $errors[] = 'Lutfen ulke / bolge secin (KKTC veya Turkiye).';
    }

    if ($errors !== []) {
        cx_flash('error', implode(' ', $errors));
        cx_redirect('/register.php?country=' . rawurlencode($country));
    }

    try {
        ListingSchemaService::ensureUserColumns();
    } catch (Throwable $e) {
        cx_flash('error', 'Veritabani guncellemesi gerekli: ' . $e->getMessage());
        cx_redirect('/register.php?country=' . rawurlencode($country));
    }

    $pdo = Database::pdo();
    $exists = $pdo->prepare('SELECT id FROM users WHERE username = ? OR email = ? LIMIT 1');
    $exists->execute([$username, $email]);
    if ($exists->fetch()) {
        cx_flash('error', 'Bu kullanici adi veya e-posta zaten kayitli.');
        cx_redirect('/register.php?country=' . rawurlencode($country));
    }

    $now = microtime(true);
    $hash = Auth::hashPassword($password);

    // Kolonlar yoksa tekrar dene
    try {
        ListingSchemaService::ensureUserColumns();
    } catch (Throwable) {
        // asagida INSERT hatasi gosterilir
    }

    try {
        $pdo->prepare(
            'INSERT INTO users (username, password_hash, role, country, email, phone, city, created_at)
             VALUES (?,?,?,?,?,?,?,?)'
        )->execute([$username, $hash, 'user', $country, $email, $phone, $city, $now]);
    } catch (Throwable $e) {
        cx_flash('error', 'Kayit basarisiz: ' . $e->getMessage() . ' — Superadmin /migrate-user-columns.php?secret=... calistirin veya phpMyAdmin: ALTER TABLE users ADD country VARCHAR(8) NOT NULL DEFAULT \'tr\';');
        cx_redirect('/register.php?country=' . rawurlencode($country));
    }

    $uid = (int) $pdo->lastInsertId();
    try {
        $pdo->prepare('UPDATE users SET country = ?, email = ?, phone = ?, city = ? WHERE id = ?')
            ->execute([$country, $email, $phone, $city, $uid]);
    } catch (Throwable) {
        try {
            $pdo->prepare('UPDATE users SET country = ?, email = ? WHERE id = ?')
                ->execute([$country, $email, $uid]);
        } catch (Throwable) {
            // ignore
        }
    }

    $token = Auth::newSession($uid);
    Auth::setTokenCookie($token);
    cx_flash('ok', $country === 'kktc'
        ? 'Hesap olusturuldu. KKTC / sterlin ilanlari acildi.'
        : 'Hesap olusturuldu.');
    cx_redirect($country === 'kktc' ? '/index.php?region=kktc' : '/index.php?region=all');
}

$googleOn = cx_google_enabled();
$preCountry = cx_normalize_country((string) ($_GET['country'] ?? 'tr'));

ob_start();
?>
<p style="margin:0 0 16px"><a class="link-gold" href="/index.php">← Ilanlara don</a></p>
<?php $compact = false; require __DIR__ . '/views/partials/brand.php'; ?>
<h1 style="text-align:center;font-size:22px;font-weight:800;margin:24px 0 20px">Kayit ol</h1>

<?php if ($googleOn): ?>
<a class="btn-google" id="google_register_btn" href="/auth/google-login.php?next=<?= rawurlencode($preCountry === 'kktc' ? '/index.php?region=kktc' : '/index.php?region=all') ?>&country=<?= cx_e($preCountry) ?>">
  <span>G</span> Google ile kayit ol
</a>
<p class="auth-divider">veya</p>
<?php endif; ?>

<form class="form" method="post" id="register_form" novalidate>
  <?= cx_csrf_field() ?>

  <p class="auth-country__label">Nereden kayit oluyorsunuz? *</p>
  <div class="auth-country__flags" role="radiogroup" aria-label="Ulke / bolge">
    <label class="auth-country__opt">
      <input type="radio" name="country" value="kktc" <?= $preCountry === 'kktc' ? 'checked' : '' ?> required>
      <span class="auth-country__card">
        <svg class="site-flags__svg" viewBox="0 0 36 24" width="40" height="26" aria-hidden="true">
          <rect width="36" height="24" fill="#fff"/>
          <rect y="0" width="36" height="3.2" fill="#e30a17"/>
          <rect y="20.8" width="36" height="3.2" fill="#e30a17"/>
          <circle cx="14.2" cy="12" r="5.1" fill="#e30a17"/>
          <circle cx="15.7" cy="12" r="4.1" fill="#fff"/>
          <polygon fill="#e30a17" points="21.2,12 19.55,12.55 20.85,11.15 20.85,12.85 19.55,11.45"/>
        </svg>
        <strong>KKTC</strong>
        <small>Sterlin · sağ/sol dümen</small>
      </span>
    </label>
    <label class="auth-country__opt">
      <input type="radio" name="country" value="tr" <?= $preCountry === 'tr' ? 'checked' : '' ?> required>
      <span class="auth-country__card">
        <svg class="site-flags__svg" viewBox="0 0 36 24" width="40" height="26" aria-hidden="true">
          <rect width="36" height="24" fill="#e30a17"/>
          <circle cx="13.5" cy="12" r="6" fill="#fff"/>
          <circle cx="15.4" cy="12" r="4.8" fill="#e30a17"/>
          <polygon fill="#fff" points="21.6,12 19.55,12.7 20.95,10.9 20.95,13.1 19.55,11.3"/>
        </svg>
        <strong>Türkiye</strong>
        <small>TL · sol dümen</small>
      </span>
    </label>
  </div>

  <label>Kullanici adi *</label>
  <input name="username" required minlength="3" autocomplete="username" maxlength="64">

  <label>E-posta *</label>
  <input name="email" type="email" required autocomplete="email" placeholder="ornek@mail.com">

  <label>GSM *</label>
  <input name="phone" type="tel" required autocomplete="tel" placeholder="0533 123 45 67" inputmode="tel">
  <p class="auth-hint" style="margin-top:-8px">Ileride SMS dogrulama icin kullanilacak.</p>

  <label>Konum / sehir *</label>
  <input name="city" required autocomplete="address-level2" placeholder="<?= $preCountry === 'kktc' ? 'Girne / Mağusa / Lefkoşa' : 'İstanbul / Ankara' ?>" id="register_city">

  <label>Sifre *</label>
  <input name="password" type="password" required minlength="6" autocomplete="new-password">

  <label>Sifre tekrar *</label>
  <input name="password2" type="password" required minlength="6" autocomplete="new-password">

  <button class="btn-primary" type="submit">Kayit ol</button>
</form>
<p style="text-align:center;margin-top:20px;font-size:13px;color:var(--muted)">
  Zaten hesabin var mi? <a href="/login.php">Giris yap</a>
</p>
<script>
(function () {
  var form = document.getElementById('register_form');
  var googleBtn = document.getElementById('google_register_btn');
  var city = document.getElementById('register_city');
  function sync() {
    var checked = form.querySelector('input[name="country"]:checked');
    var val = checked ? checked.value : 'tr';
    if (city && !city.value) {
      city.placeholder = val === 'kktc' ? 'Girne / Mağusa / Lefkoşa' : 'İstanbul / Ankara';
    }
    if (googleBtn) {
      googleBtn.href = '/auth/google-login.php?next=' + encodeURIComponent(val === 'kktc' ? '/index.php?region=kktc' : '/index.php?region=all') + '&country=' + encodeURIComponent(val);
    }
  }
  form.querySelectorAll('input[name="country"]').forEach(function (el) {
    el.addEventListener('change', sync);
  });
  sync();
})();
</script>
<?php
$content = ob_get_clean();
$title = 'Kayit';
$layout = 'auth';
$bodyClass = 'page-auth-register';
require __DIR__ . '/views/layout.php';
