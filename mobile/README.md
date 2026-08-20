# BenimBazar — Flutter Mobil Uygulaması

Android & iOS için canlı API'ye bağlı Flutter projesi.

## Kurulum

### 1. Flutter Kur (eğer kurulu değilse)
```powershell
# Windows — winget ile
winget install Google.Flutter

# Veya: https://docs.flutter.dev/get-started/install/windows
```

### 2. Bağımlılıkları Yükle
```bash
cd D:\changex\mobile
flutter pub get
```

### 3. Android Emülatör veya Gerçek Cihaz
```bash
flutter devices        # bağlı cihazları listele
flutter run            # emülatörde çalıştır
flutter run -d <id>    # belirli cihazda çalıştır
```

### 4. APK Oluştur (release)
```bash
flutter build apk --release
# Çıktı: build/app/outputs/flutter-apk/app-release.apk
```

### 5. App Bundle (Google Play için)
```bash
flutter build appbundle --release
```

---

## Proje Yapısı

```
lib/
├── main.dart                          # Uygulama başlangıcı
├── core/
│   ├── api_client.dart                # HTTP katmanı, token yönetimi
│   ├── models.dart                    # User, Listing, Message vb.
│   ├── auth_provider.dart             # Auth state (Provider)
│   └── theme.dart                     # Renk & tema
└── features/
    ├── auth/screens/
    │   ├── login_screen.dart
    │   └── register_screen.dart
    ├── listings/screens/
    │   ├── listings_screen.dart       # Arama + filtre + grid
    │   └── listing_detail_screen.dart # Detay + galeri + mesaj
    ├── favorites/
    │   └── favorites_screen.dart
    ├── messages/
    │   └── messages_screen.dart       # Konuşma listesi + chat
    ├── profile/
    │   └── profile_screen.dart        # Profil düzenleme + şifre
    └── home/
        └── home_screen.dart           # Bottom navigation
```

## API Bağlantısı

`lib/core/api_client.dart` içindeki `baseUrl` sabitini güncelle:

```dart
static const String baseUrl = 'https://yourdomain.com/api/v1';
```

## Ekranlar

| Ekran | Açıklama |
|-------|----------|
| **İlanlar** | Filtreli grid, arama, bölge seçimi, sonsuz scroll |
| **Detay** | Fotoğraf galerisi, fiyat, satıcı, arama/mesaj butonları |
| **Favoriler** | Favorileri listele/kaldır |
| **Mesajlar** | Konuşma listesi + gerçek zamanlı chat |
| **Profil** | Bilgi güncelleme, şifre değiştir, çıkış |

## Geliştirme İpuçları

- Token 90 gün geçerli, `SharedPreferences`'te saklanır
- API base URL'i `api_client.dart`'tan değiştir
- Yeni ekran eklemek için `features/` altına klasör aç, `home_screen.dart`'a tab ekle
- iOS için `ios/Runner/Info.plist`'e `NSPhotoLibraryUsageDescription` ekle
