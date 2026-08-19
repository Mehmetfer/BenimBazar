<?php

declare(strict_types=1);

/** @var array<string,mixed>|null $user */

/** @var string $navActive */

$navActive = $navActive ?? 'home';

$user = $user ?? cx_current_user();

?>

<nav class="bottom-nav" aria-label="Alt menu">

  <a class="bottom-nav__cta" href="<?= $user ? '/create-listing.php' : cx_login_url('/create-listing.php', 'İlan vermek için giriş yapın') ?>">

    <span class="bottom-nav__cta-icon">📷</span>

    Fotoğraflı ilan ver

  </a>

  <div class="bottom-nav__row">

    <a class="bottom-nav__item<?= $navActive === 'home' ? ' active' : '' ?>" href="/index.php">

      <span>🏠</span> Ana sayfa

    </a>

    <?php if ($user): ?>

    <a class="bottom-nav__item<?= $navActive === 'notifications' ? ' active' : '' ?>" href="/notifications.php">
      <span>🔔</span> Bildirimler
      <?php if (($navNotifyCount ?? 0) > 0): ?>
        <span class="bottom-nav__badge"><?= (int) $navNotifyCount ?></span>
      <?php endif; ?>
    </a>

    <a class="bottom-nav__item<?= $navActive === 'messages' ? ' active' : '' ?>" href="/messages.php">

      <span>💬</span> Mesajlar
      <?php if (cx_messages_enabled() && ($navMsgCount ?? 0) > 0): ?>
        <span class="bottom-nav__badge"><?= (int) $navMsgCount ?></span>
      <?php endif; ?>

    </a>

    <?php endif; ?>

    <?php if ($user): ?>

    <?php if (cx_is_corporate($user)): ?>
    <a class="bottom-nav__item<?= $navActive === 'gallery' ? ' active' : '' ?>" href="/gallery-panel.php">
      <span>🏢</span> Mağaza
    </a>
    <?php else: ?>
    <a class="bottom-nav__item<?= $navActive === 'mine' ? ' active' : '' ?>" href="/my-listings.php">
      <span>📋</span> İlanlarım
    </a>
    <?php endif; ?>

    <?php endif; ?>

  </div>

</nav>

