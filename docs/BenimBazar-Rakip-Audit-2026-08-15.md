# BENİMBAZAR — Rakip Platform Karşılaştırmalı UX / Özellik Audit

**Tarih:** 15 Ağustos 2026  
**Canlı site:** http://changex.mehmetfer.com.tr/  
**Yöntem:** Canlı site taraması + kod tabanı incelemesi + web araştırması

---

## Yönetici Özeti

BenimBazar, **KKTC odaklı araç ağırlıklı bir MVP marketplace**. Otomobil tarafında marka/model sihirbazı, zengin filtre şeması ve detay sayfası teknik alanları **yerel rakiplerin çoğundan güçlü**. Ancak **mesajlaşma kapalı**, **konum filtresi yok**, **SEO altyapısı zayıf**, **güven/doğrulama yüzeysel**, **monetizasyon yok**.

**Rekabet konumu:** 🟡 Rekabet edebilir MVP (KKTC araç nişinde potansiyel var)

**BENİMBAZAR 2026 REKABET SKORU: 4.3 / 10**

---

## 1. BenimBazar — Özellik Envanteri

| Alan | Durum |
|------|--------|
| Ana sayfa + arama | ✅ Canlı |
| Araç marka/model sihirbazı | ✅ Canlı |
| Gelişmiş araç filtreleri | ✅ Canlı |
| İlan detay galerisi | ✅ Canlı |
| Favori | ✅ (giriş gerekli) |
| Paylaşım / WhatsApp OG | ✅ Canlı |
| Mesajlaşma | ⚠️ Kodda var, kapalı (messages_enabled: false) |
| Bildirimler | ✅ |
| Satıcı profil sayfası | ❌ |
| Harita / benzer ilanlar / raporlama | ❌ |
| Kayıtlı arama / fiyat alarmı | ❌ |
| Konum filtresi | ❌ |
| Sitemap / robots / JSON-LD | ❌ |
| HTTPS | ❌ |
| Native mobil uygulama | ❌ |

**Canlı gözlemler:** TL/£ karışık fiyatlar; birçok ilanda 👁 0; ana sayfa ~2,4 sn yüklenme.

---

## 2. Ana Sayfa Karşılaştırması

BenimBazar araç alıcısı için TÜM ARAÇLAR + marka sihirbazı ile **odaklı**; genel marketplace beklentisinde Sahibinden ve Facebook Marketplace **daha iyi yönlendiriyor**. Konum seçimi, popüler arama, güven rozeti, native app CTA eksik.

---

## 3. İlan Kartı

Var: foto, fiyat, başlık, konum, tarih, favori, rozetler (SATILDI/TAKAS/ÖNE ÇIKAN), görüntülenme.  
Eksik: satıcı adı kartta, fiyat düşüşü, premium rozet, hızlı mesaj/ara.

---

## 4. İlan Detay

Güçlü: galeri, zengin araç specs, donanım, açıklama, teknik tablo, WhatsApp paylaşım.  
Eksik: harita, benzer ilanlar, raporla, soru-cevap, aktif mesajlaşma.

---

## 5. İlan Verme

Giriş zorunlu, tek sayfa form, zengin araç alanları, çoklu foto + kapak.  
Eksik: önizleme, konum picker, taslak kayıt.  
**En iyi genel deneyim:** Facebook Marketplace. **En iyi araç detayı:** Sahibinden.

---

## 6. Arama — Puan: 5/10

Kelime + kategori/veh var. Otomatik tamamlama, son aramalar, konum, sıralama yok.

---

## 7. Filtre

Var: fiyat, yıl, km, cc, HP, yakıt, vites, çekiş, kasa, renk, kapı, satıcı tipi.  
Eksik: konum, ilan tarihi, otomobil hasar/ekspertiz, kredi, servis geçmişi.

---

## 8. Otomobil İlanları

Marka/model sihirbazı ve teknik alanlar güçlü. Hasar, ekspertiz, kredi, konum filtresi eksik. Sağ direksiyon/Kıbrıs plakası avantaj potansiyeli.

---

## 9. Güven — Temel seviye

Moderasyon var. Telefon doğrulama rozeti, raporlama, güvenli ödeme, yorum/puan yok. Change Score gösteriliyor.

---

## 10. Kullanıcı Hesabı

İlanlarım, favoriler, bildirimler var. Profil sayfası, kayıtlı arama, mesajlar (kapalı), doğrulama UX eksik.

---

## 11. Mesajlaşma

DB + inbox iskeleti var; messages_enabled: false → **canlıda kapalı**.

---

## 12. Favoriler ve Bildirimler

Favori var. Fiyat alarmı, kayıtlı arama, push yok.

---

## 13. Mobil — 6.0/10

Responsive + bottom nav + filter drawer iyi. Native app ve mesaj eksik.

---

## 14. Tasarım

Modern, sade kart UI (7/10). Güven hissi zayıf (HTTP, 0 görüntülenme).

---

## 15. SEO — 2.5/10

Query URL, sitemap/robots yok, JSON-LD yok, HTTPS yok.

---

## 16. Gelir Modeli

Monetizasyon yok. Düşük riskli başlangıç: öne çıkarma, vitrin, ilan yenileme.

---

## 17. Özellik Matrisi (özet)

| Özellik | BenimBazar | Sahibinden | FB Market |
|---------|------------|------------|-----------|
| Arama | ⚠️ | ✅ | ✅ |
| Gelişmiş filtre | ✅ | ✅ | ⚠️ |
| Favoriler | ✅ | ✅ | ✅ |
| Mesajlaşma | ❌ | ✅ | ✅ |
| Satıcı profili | ❌ | ✅ | ✅ |
| Doğrulanmış kullanıcı | ❌ | ✅ | ⚠️ |
| Fiyat alarmı | ❌ | ✅ | ⚠️ |
| Araç filtreleri | ✅ | ✅ | ❌ |
| SEO | ❌ | ✅ | ✅ |

---

## 18. Puanlama (/10 normalize)

| Platform | Skor |
|----------|------|
| Sahibinden | 8.6 |
| eBay | 8.0 |
| Facebook Marketplace | 7.8 |
| OLX | 7.4 |
| Letgo TR | 6.8 |
| KKTC Bit Pazarı | 6.0 |
| **BenimBazar** | **4.3** |

---

## 19. Rekabet Durumu: 🟡 Rekabet edebilir MVP

---

## 20. En Güçlü 10 Yön

1. Araç marka/model sihirbazı  
2. Derin otomobil filtreleri  
3. Zengin ilan detay  
4. Takas + satış birlikte  
5. TÜM ARAÇLAR  
6. Foto filigranı  
7. WhatsApp OG paylaşım  
8. Mobil filter drawer  
9. Admin moderasyon + import  
10. Sade modern UI  

---

## 21. En Zayıf 10 Yön

1. Mesajlaşma kapalı  
2. Konum filtresi yok  
3. SEO yok  
4. HTTPS yok  
5. Satıcı profil/doğrulama yok  
6. Fiyat alarmı yok  
7. İlan raporlama yok  
8. Benzer ilanlar yok  
9. Native app yok  
10. Monetizasyon yok + karışık para birimi  

---

## 22. Rakiplerden Alınması Gereken 20 Özellik (özet)

P0: HTTPS, mesajlaşma, konum filtresi, telefon doğrulama rozeti  
P1: İlan raporlama, benzer ilanlar, hasar/ekspertiz (otomobil), kayıtlı arama, satıcı profil, SEO  
P2: Doping/vitrin, satıcı puanı, sıralama, native app, soru-cevap, ilan yenileme  

---

## 23. Farklılaştırma — 10 Fikir

1. Kıbrıs araç pasaportu (sağ direksiyon, plaka)  
2. Takas eşleştirici  
3. Girne/Lefkoşa konum preset’leri  
4. Change Score şeffaflığı  
5. Filigranlı foto standardı  
6. Cross-vehicle keşif (TÜM ARAÇLAR)  
7. WhatsApp-first paylaşım  
8. Komisyonsuz güvenli mesaj  
9. Import kalite skoru  
10. £/TL çift para normalizasyonu  

---

## İlk 10 Geliştirme

1. HTTPS  
2. Mesajlaşmayı aç  
3. KKTC konum filtresi  
4. Telefon doğrulama rozeti  
5. İlan raporlama  
6. Benzer ilanlar  
7. Favori → fiyat düşüş bildirimi  
8. Satıcı profil sayfası  
9. SEO (sitemap, robots, URL, JSON-LD)  
10. £/TL normalizasyon + sıralama  

---

# BENİMBAZAR 2026 REKABET SKORU: 4.3 / 10

Tam rapor Cursor sohbetinde üretildi. Doğrulanamadı: ilankktc.com (Cloudflare), Letgo TR/Bazaraki güncel UI canlı test edilmedi.
