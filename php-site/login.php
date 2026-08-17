<?php



declare(strict_types=1);



require __DIR__ . '/bootstrap.php';



use App\Helpers\Auth;

use App\Helpers\Database;

use App\Helpers\Security;



cx_bootstrap();



$next = cx_safe_next((string) ($_GET['next'] ?? '/index.php'));

$reason = trim((string) ($_GET['reason'] ?? ''));



if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    Security::rateLimit('login', 20, 300);

    Security::requireCsrf();



    $username = trim((string) ($_POST['username'] ?? ''));

    $password = (string) ($_POST['password'] ?? '');

    $next = cx_safe_next((string) ($_POST['next'] ?? '/index.php'));



    try {

        $stmt = Database::pdo()->prepare(

            'SELECT * FROM users WHERE username = ? LIMIT 1'

        );

        $stmt->execute([$username]);

        $row = $stmt->fetch();



        if (!$row || !Auth::verifyPassword($password, (string) $row['password_hash'])) {

            cx_flash('error', 'Kullanici adi veya sifre hatali.');

            cx_redirect('/login.php?next=' . urlencode($next));

        }

        if (cx_is_blocked_password($username, $password)) {

            cx_flash('error', 'Bu sifre guvenlik nedeniyle devre disi. Yonetici ile iletisime gecin veya yeni sifre belirleyin.');

            cx_redirect('/login.php?next=' . urlencode($next));

        }

        if ((int) ($row['suspended'] ?? 0) === 1) {

            cx_flash('error', 'Hesabiniz askiya alinmis. Destek ile iletisime gecin.');

            cx_redirect('/login.php?next=' . urlencode($next));

        }

        if (!cx_vip_can_login($row)) {

            cx_flash('error', cx_vip_login_block_message($row));

            cx_redirect('/login.php?next=' . urlencode($next));

        }



        $token = Auth::newSession((int) $row['id']);

        Auth::setTokenCookie($token);

        cx_flash('ok', 'Hos geldiniz, ' . $row['username']);

        cx_redirect($next);

    } catch (Throwable $e) {

        cx_flash('error', $e->getMessage());

        cx_redirect('/login.php');

    }

}



$googleOn = cx_google_enabled();



ob_start();

?>

<p style="margin:0 0 16px"><a class="link-gold" href="/index.php">← Ilanlara don</a></p>

<?php $compact = false; require __DIR__ . '/views/partials/brand.php'; ?>

<h1 style="text-align:center;font-size:22px;font-weight:800;margin:24px 0 8px">Giris yap</h1>

<?php if ($reason !== ''): ?>

<p class="alert alert-error" style="text-align:center"><?= cx_e($reason) ?></p>

<?php endif; ?>

<p style="text-align:center;color:var(--muted);font-size:13px;margin:0 0 20px"><?= cx_e(cx_site_tagline()) ?></p>



<?php if ($googleOn): ?>

<a class="btn-google" href="/auth/google-login.php?next=<?= urlencode($next) ?>">

  <span>G</span> Google ile devam et

</a>

<p class="auth-divider">veya</p>

<?php else: ?>

<p class="auth-hint">Google girisi icin <code>config/google.local.php</code> dosyasini yapilandirin.</p>

<?php endif; ?>



<form class="form" method="post">

  <?= cx_csrf_field() ?>

  <input type="hidden" name="next" value="<?= cx_e($next) ?>">

  <label>Kullanici adi</label>

  <input name="username" required autocomplete="username">

  <label>Sifre</label>

  <input name="password" type="password" required autocomplete="current-password">

  <p class="auth-forgot">
    <a href="/forgot-password.php?next=<?= urlencode($next) ?>">Kullanıcı adı veya şifremi unuttum</a>
  </p>

  <button class="btn-primary" type="submit">Giris yap</button>

</form>

<p style="text-align:center;margin-top:20px;font-size:13px;color:var(--muted)">

  Hesabin yok mu? <a href="/register.php">Kayit ol</a>

</p>

<?php

$content = ob_get_clean();

$title = 'Giris';

$layout = 'auth';

require __DIR__ . '/views/layout.php';

