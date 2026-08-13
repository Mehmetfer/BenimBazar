# Varmisin

Flutter UI iskeleti — gerçek yerel login/kayıt, oturum saklama.

## Özellikler

- Splash
- Kayıt / giriş (`AuthService` — SharedPreferences + SHA-256)
- Oturum kalıcı; çıkış temizler
- Lobi + örnek ekranlar (başka ürüne taşımak için kabuk)

Auth katmanı (`lib/auth/auth_service.dart`) sonra Firebase/Supabase ile değiştirilebilir.

## Çalıştır

```bash
flutter pub get
flutter run -d chrome
```

## Not

Bu bir tasarım/iskelet projesidir. Gerçek kumar / ödeme yoktur.
