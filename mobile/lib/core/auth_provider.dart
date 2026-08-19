import 'package:flutter/foundation.dart';
import 'api_client.dart';
import 'models.dart';

class AuthProvider extends ChangeNotifier {
  User? _user;
  bool _loading = false;
  String? _error;

  User? get user => _user;
  bool get loading => _loading;
  String? get error => _error;
  bool get isLoggedIn => _user != null;

  // Uygulama açılışında token varsa kullanıcıyı yükle
  Future<void> init() async {
    final token = await ApiClient.getToken();
    if (token == null) return;
    final resp = await ApiClient.get('/auth/me', auth: true);
    if (resp.ok && resp.data != null) {
      _user = User.fromJson(resp.data as Map<String, dynamic>);
      notifyListeners();
    } else if (resp.isUnauthorized) {
      await ApiClient.clearToken();
    }
  }

  Future<String?> login(String username, String password) async {
    _loading = true;
    _error = null;
    notifyListeners();

    final resp = await ApiClient.post('/auth/login', {
      'username': username,
      'password': password,
    });

    _loading = false;
    if (resp.ok && resp.data != null) {
      final data = resp.data as Map<String, dynamic>;
      await ApiClient.saveToken(data['token'] as String);
      _user = User.fromJson(data['user'] as Map<String, dynamic>);
      notifyListeners();
      return null; // başarı
    }
    _error = resp.error ?? 'Giriş başarısız.';
    notifyListeners();
    return _error;
  }

  Future<String?> register({
    required String username,
    required String password,
    required String email,
    required String phone,
    required String city,
    required String country,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    final resp = await ApiClient.post('/auth/register', {
      'username': username,
      'password': password,
      'email': email,
      'phone': phone,
      'city': city,
      'country': country,
    });

    _loading = false;
    if (resp.ok && resp.data != null) {
      final data = resp.data as Map<String, dynamic>;
      await ApiClient.saveToken(data['token'] as String);
      _user = User.fromJson(data['user'] as Map<String, dynamic>);
      notifyListeners();
      return null;
    }
    _error = resp.error ?? 'Kayıt başarısız.';
    notifyListeners();
    return _error;
  }

  Future<void> logout() async {
    await ApiClient.post('/auth/logout', {}, auth: true);
    await ApiClient.clearToken();
    _user = null;
    notifyListeners();
  }

  Future<void> refreshMe() async {
    final resp = await ApiClient.get('/auth/me', auth: true);
    if (resp.ok && resp.data != null) {
      _user = User.fromJson(resp.data as Map<String, dynamic>);
      notifyListeners();
    }
  }
}
