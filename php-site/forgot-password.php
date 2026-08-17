<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/PasswordResetService.php';

use App\Helpers\Security;
use App\Services\PasswordResetService;

cx_bootstrap();

if (cx_current_user() !== null) {
    cx_redirect('/index.php');
}

$next = cx_safe_next((string) ($_GET['next'] ?? '/login.php'));
$challenge = PasswordResetService::challenge();
$step = $challenge !== null ? 'reset' : 'verify';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::rateLimit('forgot_password', 12, 600);
    Security::requireCsrf();

    $action = (string) ($_POST['action'] ?? '');
    $next = cx_safe_next((string) ($_POST['next'] ?? '/login.php'));

    try {
        if ($action === 'verify') {
            $phone = trim((string) ($_POST['phone'] ?? ''));
            $email = trim((string) ($_POST['email'] ?? ''));
            $phoneDigits = cx_phone_digits($phone);
            if ($phoneDigits === '' || strlen($phoneDigits) < 10) {
                throw new RuntimeException('Geçerli bir cep telefonu girin.');
            }
            if ($email === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
                throw new RuntimeException('Geçerli bir e-posta girin.');
            }

            $found = PasswordResetService::findByPhoneAndEmail($phone, $email);
            if ($found === null) {
                // Hesap var/yok sızdırmamak için genel mesaj
                throw new RuntimeException(
                    'Bu cep telefonu ve e-posta ile eşleşen hesap bulunamadı. '
                    . 'Kayıtlı bilgilerinizi kontrol edin.'
                );
            }

            PasswordResetService::startChallenge($found['id'], $found['username']);
            cx_flash('ok', 'Hesabınız doğrulandı. Kullanıcı adınızı görün ve yeni şifre belirleyin.');
            cx_redirect('/forgot-password.php?next=' . rawurlencode($next));
        }

        if ($action === 'reset') {
            $token = (string) ($_POST['reset_token'] ?? '');
            $password = (string) ($_POST['password'] ?? '');
            $password2 = (string) ($_POST['password2'] ?? '');
            $ch = PasswordResetService::assertChallengeToken($token);

            if ($password !== $password2) {
                throw new RuntimeException('Şifre tekrarı eşleşmiyor.');
            }
            if (cx_is_blocked_password($ch['username'], $password)) {
                throw new RuntimeException('Bu şifre güvenlik nedeniyle kullanılamaz. Başka bir şifre seçin.');
            }

            PasswordResetService::updatePassword($ch['user_id'], $password);
            PasswordResetService::clearChallenge();
            cx_flash('ok', 'Şifreniz güncellendi. Yeni şifrenizle giriş yapabilirsiniz.');
            cx_redirect('/login.php?next=' . rawurlencode($next));
        }

        if ($action === 'cancel') {
            PasswordResetService::clearChallenge();
            cx_redirect('/forgot-password.php?next=' . rawurlencode($next));
        }

        throw new RuntimeException('Geçersiz işlem.');
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
        cx_redirect('/forgot-password.php?next=' . rawurlencode($next));
    }
}

$challenge = PasswordResetService::challenge();
$step = $challenge !== null ? 'reset' : 'verify';

ob_start();
?>
<p style="margin:0 0 16px"><a class="link-gold" href="/login.php?next=<?= rawurlencode($next) ?>">← Girişe dön</a></p>
<?php $compact = false; require __DIR__ . '/views/partials/brand.php'; ?>
<h1 style="text-align:center;font-size:22px;font-weight:800;margin:24px 0 8px">Kullanıcı adı / şifre hatırlatma</h1>
<p class="auth-hint" style="margin-bottom:20px">
  Kayıtlı <strong>cep telefonu</strong> ve <strong>e-posta</strong> adresinizle hesabınızı doğrulayın.
  Kullanıcı adınızı görün ve yeni şifre belirleyin.
</p>

<?php if ($step === 'verify'): ?>
<form class="form" method="post" autocomplete="on">
  <?= cx_csrf_field() ?>
  <input type="hidden" name="action" value="verify">
  <input type="hidden" name="next" value="<?= cx_e($next) ?>">

  <label for="forgot_phone">Cep telefonu</label>
  <input id="forgot_phone" name="phone" type="tel" required autocomplete="tel"
         placeholder="0533 123 45 67" inputmode="tel">

  <label for="forgot_email">E-posta</label>
  <input id="forgot_email" name="email" type="email" required autocomplete="email"
         placeholder="ornek@mail.com">

  <button class="btn-primary" type="submit">Doğrula ve devam et</button>
</form>
<?php else: ?>
<div class="forgot-user-box" role="status">
  <span class="forgot-user-box__label">Kullanıcı adınız</span>
  <strong class="forgot-user-box__name"><?= cx_e($challenge['username']) ?></strong>
</div>

<form class="form" method="post" autocomplete="off">
  <?= cx_csrf_field() ?>
  <input type="hidden" name="action" value="reset">
  <input type="hidden" name="next" value="<?= cx_e($next) ?>">
  <input type="hidden" name="reset_token" value="<?= cx_e($challenge['token']) ?>">

  <label for="forgot_password">Yeni şifre</label>
  <input id="forgot_password" name="password" type="password" required minlength="6"
         autocomplete="new-password">

  <label for="forgot_password2">Yeni şifre (tekrar)</label>
  <input id="forgot_password2" name="password2" type="password" required minlength="6"
         autocomplete="new-password">

  <button class="btn-primary" type="submit">Şifreyi güncelle</button>
</form>

<form method="post" class="forgot-cancel">
  <?= cx_csrf_field() ?>
  <input type="hidden" name="action" value="cancel">
  <input type="hidden" name="next" value="<?= cx_e($next) ?>">
  <button class="link-gold forgot-cancel__btn" type="submit">Farklı hesap ile dene</button>
</form>
<?php endif; ?>

<p style="text-align:center;margin-top:20px;font-size:13px;color:var(--muted)">
  Şifrenizi hatırladınız mı? <a href="/login.php?next=<?= rawurlencode($next) ?>">Giriş yap</a>
</p>
<?php
$content = ob_get_clean();
$title = 'Şifremi unuttum';
$layout = 'auth';
$bodyClass = 'page-auth-forgot';
require __DIR__ . '/views/layout.php';
