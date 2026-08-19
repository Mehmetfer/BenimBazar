<?php



declare(strict_types=1);



require __DIR__ . '/bootstrap.php';

require_once __DIR__ . '/app/Services/MessageService.php';



use App\Services\MessageService;



cx_bootstrap();



if (!cx_messages_enabled()) {

    cx_flash('error', 'Mesajlaşma şu an kapalı.');

    cx_redirect('/index.php');

}



$user = cx_require_user();

$msgSvc = new MessageService();

$inbox = $msgSvc->inbox((int) $user['id']);



ob_start();

?>

<h1 class="section-title">Mesajlar</h1>

<p class="section-sub">Güvenli mesajlaşma — telefon numarası paylaşılmaz.</p>



<?php if ($inbox === []): ?>

<div class="empty-state">

  Henüz mesajınız yok.<br>

  Bir ilan detayından mesaj başlatabilirsiniz.

</div>

<p style="text-align:center;margin-top:16px"><a class="link-gold" href="/index.php">İlanlara dön</a></p>

<?php else: ?>

<ul class="msg-list">

<?php foreach ($inbox as $row): ?>

  <?php

    $convId = (int) ($row['id'] ?? 0);

    $unread = (int) ($row['unread_count'] ?? 0);

    $listingTitle = trim((string) ($row['listing_title'] ?? ''));

    $other = trim((string) ($row['other_username'] ?? ''));

    $headline = $listingTitle !== '' ? $listingTitle : ('Galeri · ' . ($other !== '' ? $other : 'Sohbet'));

  ?>

  <li class="msg-item<?= $unread > 0 ? ' msg-item--unread' : '' ?>">

    <a class="msg-item__link" href="/conversation.php?id=<?= $convId ?>">

      <span class="msg-item__head">

        <strong><?= cx_e($headline) ?></strong>

        <?php if ($unread > 0): ?>

        <span class="msg-item__badge"><?= $unread ?></span>

        <?php endif; ?>

      </span>

      <?php if ($other !== '' && $listingTitle !== ''): ?>

      <span class="msg-item__peer"><?= cx_e($other) ?></span>

      <?php endif; ?>

      <span class="msg-item__preview"><?= cx_e(mb_substr((string) ($row['last_body'] ?? ''), 0, 100)) ?></span>

    </a>

  </li>

<?php endforeach; ?>

</ul>

<?php endif; ?>

<?php

$content = ob_get_clean();

$title = 'Mesajlar';

$layout = 'app';

$navActive = 'messages';

require __DIR__ . '/views/layout.php';

