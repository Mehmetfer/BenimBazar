<?php

declare(strict_types=1);
?>
<footer class="site-legal-footer">
  <a href="/hakkimizda.php">Hakkımızda</a>
  <span aria-hidden="true">·</span>
  <a href="/sss.php">SSS</a>
  <span aria-hidden="true">·</span>
  <a href="/iletisim.php">İletişim</a>
  <span aria-hidden="true">·</span>
  <a href="/kullanim-kosullari.php">Kullanım koşulları</a>
  <span aria-hidden="true">·</span>
  <a href="/gizlilik.php">Gizlilik</a>
  <span aria-hidden="true">·</span>
  <a href="/kvkk.php">KVKK</a>
  <?php if (($gbp = cx_seo_google_profile_link()) !== ''): ?>
  <span aria-hidden="true">·</span>
  <a href="<?= cx_e($gbp) ?>" rel="noopener noreferrer">Google'da bizi bulun</a>
  <?php endif; ?>
</footer>
