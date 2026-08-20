<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/PhoneVerificationService.php';

use App\Helpers\Security;
use App\Services\PhoneVerificationService;

cx_bootstrap();
$user = cx_require_user();
$uid = (int) $user['id'];
$svc = new PhoneVerificationService();
$verified = PhoneVerificationService::isVerifiedUser($user);
$pending = $svc->latestPending($uid);
$debugMode = cx_phone_verify_debug_mode();
$defaultChannel = (string) (cx_phone_verify_settings()['default_channel'] ?? 'whatsapp');
$phone = trim((string) ($user['phone'] ?? ''));

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    try {
        if (isset($_POST['send_code'])) {
            $phoneInput = trim((string) ($_POST['phone'] ?? $phone));
            $channel = (string) ($_POST['channel'] ?? $defaultChannel);
            $result = $svc->sendCode($uid, $phoneInput, $channel);
            $phone = $phoneInput;
            $pending = $svc->latestPending($uid);
            $chLabel = $result['channel'] === 'whatsapp' || str_contains($result['channel'], 'whatsapp')
                ? 'WhatsApp'
                : 'SMS';
            cx_flash('ok', 'Dogrulama kodu gonderildi (' . $chLabel . ').');
            if (!empty($result['debug_code']) && $debugMode) {
                \App\Helpers\Session::set('cx_verify_debug_code', (string) $result['debug_code']);
            }
        } elseif (isset($_POST['confirm_code'])) {
            $svc->confirmCode($uid, (string) ($_POST['code'] ?? ''));
            \App\Helpers\Session::set('cx_verify_debug_code', null);
            cx_flash('ok', 'Telefon numaraniz dogrulandi.');
            cx_redirect('/my-listings.php');
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    cx_redirect('/verify-phone.php');
}

$debugCode = (string) \App\Helpers\Session::get('cx_verify_debug_code', '');

ob_start();
?>
<p><a class="link-gold" href="/my-listings.php">← İlanlarım</a></p>

<h1 class="section-title">Telefon doğrulama</h1>

<?php if ($verified): ?>
<div class="alert alert-ok">
  Telefonunuz doğrulanmış. <?= cx_phone_verified_badge_html('phone-verified-badge phone-verified-badge--inline') ?>
</div>
<p class="section-sub">Numara: <strong><?= cx_e($phone) ?></strong></p>
<p><a class="link-gold" href="/my-listings.php">İlanlarıma dön</a></p>

<?php else: ?>

<p class="section-sub">
  Güvenilir satıcı rozeti için telefonunuzu doğrulayın.
  <?php if ($debugMode): ?>
  <br><em>Geliştirme modu: kod ekranda gösterilir (canlı SMS/WhatsApp kapalı).</em>
  <?php endif; ?>
</p>

<?php if ($debugCode !== '' && $debugMode): ?>
<div class="verify-debug-box" role="status">
  <strong>Test kodu:</strong> <code class="verify-debug-box__code"><?= cx_e($debugCode) ?></code>
  <span class="verify-debug-box__hint">— Canlıda bu kutu görünmez; kod WhatsApp veya SMS ile gider.</span>
</div>
<?php endif; ?>

<form class="verify-form" method="post">
  <?= cx_csrf_field() ?>
  <label for="verify-phone">Telefon numaranız</label>
  <input class="create-input" id="verify-phone" name="phone" type="tel" required
         value="<?= cx_e($phone) ?>" placeholder="0533 123 45 67" autocomplete="tel">

  <fieldset class="verify-form__channels">
    <legend>Kodu nasıl almak istersiniz?</legend>
    <label class="verify-form__channel">
      <input type="radio" name="channel" value="whatsapp"<?= $defaultChannel !== 'sms' ? ' checked' : '' ?>>
      WhatsApp
    </label>
    <label class="verify-form__channel">
      <input type="radio" name="channel" value="sms"<?= $defaultChannel === 'sms' ? ' checked' : '' ?>>
      SMS
    </label>
  </fieldset>

  <button class="btn-primary" type="submit" name="send_code" value="1">Kod gönder</button>
</form>

<?php if ($pending !== null): ?>
<form class="verify-form verify-form--confirm" method="post">
  <?= cx_csrf_field() ?>
  <label for="verify-code">Doğrulama kodu</label>
  <input class="create-input verify-form__code" id="verify-code" name="code" inputmode="numeric"
         pattern="[0-9]{4,8}" maxlength="8" required placeholder="6 haneli kod" autocomplete="one-time-code">
  <button class="btn-primary" type="submit" name="confirm_code" value="1">Doğrula</button>
</form>
<?php endif; ?>

<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Telefon doğrulama';
$layout = 'app';
$navActive = 'mine';
require __DIR__ . '/views/layout.php';
