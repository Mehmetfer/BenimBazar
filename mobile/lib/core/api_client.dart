import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiClient {
  static const String baseUrl = 'https://changex.mehmetfer.com.tr/api/v1';
  static const String _tokenKey = 'auth_token';

  // ─── Token yönetimi ──────────────────────────────────────────────
  static Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  static Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  static Future<void> clearToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  // ─── Ortak header'lar ────────────────────────────────────────────
  static Future<Map<String, String>> _headers({bool auth = false}) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'X-Platform': 'android',
      'X-App-Version': '1.0.0',
    };
    if (auth) {
      final token = await getToken();
      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      }
    }
    return headers;
  }

  // ─── HTTP metodları ──────────────────────────────────────────────
  static Future<ApiResponse> get(
    String path, {
    Map<String, String>? query,
    bool auth = false,
  }) async {
    var uri = Uri.parse('$baseUrl$path');
    if (query != null && query.isNotEmpty) {
      uri = uri.replace(queryParameters: query);
    }
    try {
      final resp = await http
          .get(uri, headers: await _headers(auth: auth))
          .timeout(const Duration(seconds: 15));
      return ApiResponse.from(resp);
    } catch (e) {
      return ApiResponse.networkError(e.toString());
    }
  }

  static Future<ApiResponse> post(
    String path,
    Map<String, dynamic> body, {
    bool auth = false,
  }) async {
    try {
      final resp = await http
          .post(
            Uri.parse('$baseUrl$path'),
            headers: await _headers(auth: auth),
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 15));
      return ApiResponse.from(resp);
    } catch (e) {
      return ApiResponse.networkError(e.toString());
    }
  }

  static Future<ApiResponse> patch(
    String path,
    Map<String, dynamic> body, {
    bool auth = true,
  }) async {
    try {
      final resp = await http
          .patch(
            Uri.parse('$baseUrl$path'),
            headers: await _headers(auth: auth),
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 15));
      return ApiResponse.from(resp);
    } catch (e) {
      return ApiResponse.networkError(e.toString());
    }
  }

  static Future<ApiResponse> delete(
    String path, {
    Map<String, String>? query,
    bool auth = true,
  }) async {
    var uri = Uri.parse('$baseUrl$path');
    if (query != null) {
      uri = uri.replace(queryParameters: query);
    }
    try {
      final resp = await http
          .delete(uri, headers: await _headers(auth: auth))
          .timeout(const Duration(seconds: 15));
      return ApiResponse.from(resp);
    } catch (e) {
      return ApiResponse.networkError(e.toString());
    }
  }
}

// ─── API Yanıt sarmalayıcı ────────────────────────────────────────
class ApiResponse {
  final bool ok;
  final dynamic data;
  final String? error;
  final String? code;
  final int statusCode;

  const ApiResponse({
    required this.ok,
    required this.statusCode,
    this.data,
    this.error,
    this.code,
  });

  factory ApiResponse.from(http.Response resp) {
    final Map<String, dynamic> json =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ApiResponse(
      ok: json['ok'] == true,
      statusCode: resp.statusCode,
      data: json['data'],
      error: json['error'] as String?,
      code: json['code'] as String?,
    );
  }

  factory ApiResponse.networkError(String message) => ApiResponse(
        ok: false,
        statusCode: 0,
        error: 'Bağlantı hatası: $message',
        code: 'NETWORK_ERROR',
      );

  bool get isUnauthorized => statusCode == 401;
}
