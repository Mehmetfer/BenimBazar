# BenimBazar Mobil REST API — v1

Android ve iOS uygulamaları için REST API altyapısı.  
Base URL: `https://yourdomain.com/api/v1`

---

## Kimlik Doğrulama

Tüm korumalı endpoint'ler `Authorization` header'ı gerektirir:

```
Authorization: Bearer <token>
```

Token, login veya register endpoint'inden alınır (90 gün geçerli).

---

## Yanıt Formatı

```json
// Başarı
{ "ok": true, "data": { ... } }

// Hata
{ "ok": false, "error": "Hata mesajı", "code": "ERROR_CODE" }
```

---

## Endpoint'ler

### Auth

| Method | URL | Auth | Açıklama |
|--------|-----|------|----------|
| POST | `/auth/login` | — | Giriş yap, token al |
| POST | `/auth/register` | — | Kayıt ol, token al |
| POST | `/auth/logout` | ✓ | Oturumu kapat |
| GET | `/auth/me` | ✓ | Mevcut kullanıcı bilgisi |

#### POST /auth/login
```json
// Request
{ "username": "kullanici", "password": "sifre123" }
// veya e-posta ile
{ "email": "mail@example.com", "password": "sifre123" }

// Response
{
  "ok": true,
  "data": {
    "token": "abc123...",
    "expires_at": 1780000000,
    "user": { "id": 1, "username": "...", "role": "user", "country": "tr", "score": 0 }
  }
}
```

#### POST /auth/register
```json
// Request
{
  "username": "yenikullanici",
  "password": "sifre123",
  "email": "mail@example.com",
  "phone": "05331234567",
  "city": "Istanbul",
  "country": "tr"
}
```

---

### İlanlar

| Method | URL | Auth | Açıklama |
|--------|-----|------|----------|
| GET | `/listings` | isteğe bağlı | İlan listesi |
| GET | `/listings/detail?id=X` | isteğe bağlı | İlan detayı |
| GET | `/listings/my` | ✓ | Kendi ilanlarım |
| GET | `/listings/favorites` | ✓ | Favorilerim |
| POST | `/listings/favorites?id=X` | ✓ | Favoriye ekle |
| DELETE | `/listings/favorites?id=X` | ✓ | Favoriden çıkar |

#### GET /listings (Query Params)
| Parametre | Tür | Varsayılan | Açıklama |
|-----------|-----|------------|----------|
| `q` | string | — | Arama terimi |
| `category` | string | — | Kategori slug |
| `region` | string | `all` | `tr` \| `kktc` \| `all` |
| `sort` | string | `new` | `new` \| `price_asc` \| `price_desc` \| `popular` |
| `page` | int | `1` | Sayfa numarası |
| `per_page` | int | `20` | Sayfa başına ilan (max 100) |
| `include_sold` | int | `0` | Satılmışları dahil et |

---

### Mesajlar

| Method | URL | Auth | Açıklama |
|--------|-----|------|----------|
| GET | `/messages` | ✓ | Konuşma listesi |
| GET | `/messages?conv=X` | ✓ | Konuşma mesajları |
| POST | `/messages` | ✓ | Mesaj gönder |

#### POST /messages
```json
// Mevcut konuşmaya
{ "conversation_id": 5, "body": "Merhaba!" }

// İlana yeni mesaj
{ "listing_id": 123, "body": "Bu ilan hala satılık mı?" }
```

---

### Kullanıcı

| Method | URL | Auth | Açıklama |
|--------|-----|------|----------|
| GET | `/user/profile` | ✓ | Profil bilgisi |
| PATCH | `/user/profile` | ✓ | Profil güncelle |
| POST | `/user/profile` | ✓ | Şifre değiştir |
| GET | `/user/notifications` | ✓ | Bildirimler |
| POST | `/user/notifications` | ✓ | Tümünü okundu işaretle |

#### PATCH /user/profile
```json
// Güncellenebilir alanlar: city, phone, country
{ "city": "Ankara", "phone": "05551234567" }
```

#### POST /user/profile (şifre değiştir)
```json
{ "current_password": "eskisifre", "new_password": "yenisifre123" }
```

---

## HTTP Durum Kodları

| Kod | Anlam |
|-----|-------|
| 200 | Başarılı |
| 201 | Oluşturuldu |
| 204 | Başarılı (içerik yok) |
| 400 | İstek hatası |
| 401 | Kimlik doğrulama gerekli |
| 403 | Yetkisiz erişim |
| 404 | Bulunamadı |
| 405 | Metod izin verilmiyor |
| 409 | Çakışma (kullanıcı zaten var) |
| 422 | Validasyon hatası |
| 429 | Çok fazla istek |
| 500 | Sunucu hatası |

---

## CORS

Tüm endpoint'ler `Access-Control-Allow-Origin: *` ile CORS'a açıktır.  
Android ve iOS native uygulamalar için ek bir ayar gerekmez.  
Capacitor / React Native / Flutter için standart `http` client kullanılabilir.

---

## Örnek Flutter / Dart Kullanımı

```dart
final resp = await http.post(
  Uri.parse('https://yourdomain.com/api/v1/auth/login'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({'username': 'user', 'password': 'pass'}),
);
final data = jsonDecode(resp.body);
final token = data['data']['token'];

// Korumalı endpoint
final listings = await http.get(
  Uri.parse('https://yourdomain.com/api/v1/listings?region=tr&per_page=20'),
  headers: {'Authorization': 'Bearer $token'},
);
```

## Örnek Kotlin / Android Kullanımı

```kotlin
val client = OkHttpClient()
val body = """{"username":"user","password":"pass"}""".toRequestBody("application/json".toMediaType())
val request = Request.Builder()
    .url("https://yourdomain.com/api/v1/auth/login")
    .post(body)
    .build()
client.newCall(request).execute().use { response ->
    val json = JSONObject(response.body!!.string())
    val token = json.getJSONObject("data").getString("token")
}
```

## Örnek Swift / iOS Kullanımı

```swift
var request = URLRequest(url: URL(string: "https://yourdomain.com/api/v1/auth/login")!)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = try? JSONSerialization.data(withJSONObject: ["username":"user","password":"pass"])

URLSession.shared.dataTask(with: request) { data, _, _ in
    if let data = data,
       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
       let dataObj = json["data"] as? [String: Any],
       let token = dataObj["token"] as? String {
        // token'ı Keychain'e kaydet
    }
}.resume()
```
