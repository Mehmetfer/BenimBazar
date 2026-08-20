<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

cx_bootstrap();

ob_start();
?>
<article class="legal-page">
  <p class="legal-page__back"><a class="link-gold" href="/index.php">← Ana sayfa</a></p>
  <h1 class="section-title">BenimBazar Araç Ekspertiz Kullanım ve Sorumluluk Koşulları</h1>
  <p class="section-sub">Son güncelleme: 15.08.2026</p>

  <div class="legal-page__body">
    <h2>1. Ekspertiz sisteminin amacı</h2>
    <p>BenimBazar’daki interaktif ekspertiz alanı <strong>yalnızca otomobil</strong> ilanlarında kullanılır; araç üzerindeki belirli kaporta parçalarının durumunu görselleştirmek, ilan sahibinin girdiği bilgileri düzenli göstermek ve alıcıya ilanı daha anlaşılır kılmak içindir.</p>
    <p>Bu alan <strong>tek başına resmi veya bağımsız bir ekspertiz raporu değildir</strong>. BenimBazar, aracın fiziksel incelemesini yapmış sayılmaz.</p>

    <h2>2. Bilgilerin kaynağı</h2>
    <p>Ekspertiz bilgileri (parça işaretleri ve varsa yüklenen rapor görselleri), kural olarak <strong>ilan sahibi</strong> tarafından ilan oluşturma veya düzenleme sırasında girilir. Yetkili personelin ilanı genel olarak düzenleyebildiği durumlar saklıdır.</p>
    <p>İlan detayında gördüğünüz ekspertiz içeriği, BenimBazar’ın bağımsız saha incelemesinin sonucu olarak sunulmaz.</p>

    <h2>3. BenimBazar’ın konumu</h2>
    <p>BenimBazar bir ilan platformudur. Platform:</p>
    <ul>
      <li>aracın kaporta / boya durumunu kendisi yerinde incelemez,</li>
      <li>girilen ekspertiz bilgilerinin doğruluğunu otomatik doğrulamaz,</li>
      <li>bağımsız bir ekspertiz kuruluşu gibi hareket etmez.</li>
    </ul>
    <p>Alım-satım kararı ve ek kontroller (bağımsız ekspertiz, belge kontrolü vb.) taraflara aittir.</p>

    <h2>4. Parça durumları</h2>
    <p>Sistemde şu an seçilebilen durumlar (ekspertiz kısaltmaları):</p>
    <ul>
      <li>Orijinal (O)</li>
      <li>Boyalı (B)</li>
      <li>Lokal boyalı (LB)</li>
      <li>Plastik (P)</li>
      <li>Değişmiş (D)</li>
      <li>Sökme/takma (ST)</li>
      <li>Vernik (V)</li>
      <li>Ezik (E)</li>
    </ul>
    <p>Bir parça için tek bir durum kaydedilir. Durumlar, giren kullanıcının beyanına dayanır.</p>
    <p>İşaretlenebilen parçalar (mevcut şema): ön/arka tampon, kaput, tavan, bagaj kapağı, sol/sağ ön ve arka çamurluklar, sol/sağ ön ve arka kapılar.</p>

    <h2>5. Boya ölçümü</h2>
    <p>Şu anki sürümde boya kalınlığı (µm) alanı bulunmamaktadır. İleride eklenirse µm değeri yalnızca sisteme girilen ölçüm bilgisini ifade eder; tek başına kesin “orijinal / boyalı” sonucu doğurmaz.</p>

    <h2>6. Fotoğraflar</h2>
    <p>İlan fotoğrafları ve (isteğe bağlı) ekspertiz rapor sayfası görselleri yüklenebilir. Fotoğraflar mevcut yükleme kurallarına (tür, boyut vb.) tabidir. Görseller, aracın tüm durumunu tek başına kanıtlamaz; yanıltıcı veya başkasına ait görseller kullanılamaz.</p>

    <h2>7. Yüklenen ekspertiz belgesi</h2>
    <p>Kullanıcı gerçek bir ekspertiz raporunun sayfalarını görsel olarak ekleyebilir. Yüklenen belge ile şema üzerindeki işaretlerin uyumu giren kullanıcının sorumluluğundadır; BenimBazar otomatik eşleştirme yapmaz.</p>

    <h2>8. Şase / mekanik</h2>
    <p>Mevcut ekspertiz şemasında şase, podye, motor, şanzıman vb. ayrı ekspertiz alanları yoktur. Bu koşullar yalnızca mevcut kaporta / parça işaretlerini kapsar.</p>

    <h2>9. Türkiye ve KKTC</h2>
    <p>Hizmet Türkiye ve KKTC kullanıcılarına açıktır. İlgili ülke veya bölgedeki yürürlükteki mevzuat saklıdır.</p>
    <p class="legal-page__note">Ülkeye özgü zorunlu metinler için hukuki inceleme gerekir.</p>

    <h2>10. Kullanıcı beyanı</h2>
    <p>Ekspertiz bilgisi giren kullanıcı, bilgilerin kendisine ait ve doğru olduğunu; eksik veya hatalı bilgiden doğabilecek sonuçların sorumluluğunun kendisine ait olduğunu; BenimBazar’ın bu bilgileri bağımsız ekspertiz olarak sunmadığını kabul etmiş sayılır (ilan formunda ayrıca onay kutusu eklenebilir).</p>

    <p><a class="link-gold" href="/kullanim-kosullari.php">← Genel kullanım koşulları</a></p>
  </div>
</article>
<?php
$content = ob_get_clean();
$title = 'Ekspertiz Koşulları';
$layout = 'app';
$navActive = 'home';
require __DIR__ . '/views/layout.php';
