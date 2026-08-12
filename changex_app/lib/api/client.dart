import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ChangeXApi {
  ChangeXApi({String? baseUrl}) : baseUrl = baseUrl ?? _defaultBase;

  static const _defaultBase = String.fromEnvironment(
    'CHANGEX_API',
    defaultValue: '',
  );

  final String baseUrl;
  static const _tokenKey = 'changex_token_v1';

  String get _root {
    if (baseUrl.isNotEmpty) return baseUrl;
    // Same origin when served by FastAPI static host.
    return Uri.base.origin;
  }

  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  Future<void> setToken(String? token) async {
    final prefs = await SharedPreferences.getInstance();
    if (token == null) {
      await prefs.remove(_tokenKey);
    } else {
      await prefs.setString(_tokenKey, token);
    }
  }

  Future<Map<String, String>> _headers({bool auth = false}) async {
    final h = {'Content-Type': 'application/json'};
    if (auth) {
      final t = await getToken();
      if (t != null) h['Authorization'] = 'Bearer $t';
    }
    return h;
  }

  Future<Map<String, dynamic>> register(String username, String password) async {
    final res = await http.post(
      Uri.parse('$_root/api/auth/register'),
      headers: await _headers(),
      body: jsonEncode({'username': username, 'password': password}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final res = await http.post(
      Uri.parse('$_root/api/auth/login'),
      headers: await _headers(),
      body: jsonEncode({'username': username, 'password': password}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>?> me() async {
    final t = await getToken();
    if (t == null) return null;
    final res = await http.get(
      Uri.parse('$_root/api/auth/me'),
      headers: await _headers(auth: true),
    );
    if (res.statusCode == 401) {
      await setToken(null);
      return null;
    }
    return _decode(res);
  }

  Future<List<dynamic>> listings({String? q, String? category}) async {
    final qp = <String, String>{};
    if (q != null && q.isNotEmpty) qp['q'] = q;
    if (category != null && category.isNotEmpty) qp['category'] = category;
    final uri = Uri.parse('$_root/api/listings').replace(queryParameters: qp.isEmpty ? null : qp);
    final res = await http.get(uri, headers: await _headers(auth: true));
    final data = _decode(res);
    return (data['listings'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> createListing(Map<String, dynamic> body) async {
    final res = await http.post(
      Uri.parse('$_root/api/listings'),
      headers: await _headers(auth: true),
      body: jsonEncode(body),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> createOffer(Map<String, dynamic> body) async {
    final res = await http.post(
      Uri.parse('$_root/api/trades/offer'),
      headers: await _headers(auth: true),
      body: jsonEncode(body),
    );
    return _decode(res);
  }

  Future<List<dynamic>> myTrades() async {
    final res = await http.get(
      Uri.parse('$_root/api/trades/mine'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['trades'] as List?) ?? [];
  }

  Map<String, dynamic> _decode(http.Response res) {
    Map<String, dynamic> body;
    try {
      final decoded = jsonDecode(res.body);
      body = decoded is Map<String, dynamic>
          ? decoded
          : <String, dynamic>{'data': decoded};
    } catch (_) {
      body = {'detail': res.body};
    }
    if (res.statusCode >= 400) {
      final detail = body['detail'];
      String message;
      if (detail is Map) {
        message = detail['message']?.toString() ?? detail.toString();
      } else {
        message = detail?.toString() ?? 'İstek başarısız (${res.statusCode})';
      }
      throw ApiException(message);
    }
    return body;
  }
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

final api = ChangeXApi();
