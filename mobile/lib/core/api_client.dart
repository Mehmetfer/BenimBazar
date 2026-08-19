import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiClient {
  /// Sunucuda HTTPS sertifikasi gecersiz; HTTP + mobil-api.php router kullanilir.
  static const String baseUrl = 'http://changex.mehmetfer.com.tr/mobil-api.php';
  static const String _tokenKey = 'auth_token';

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

  static Future<Map<String, String>> _headers({bool auth = false}) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
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

  static Uri _uri(String path, [Map<String, String>? query]) {
    final route = path.startsWith('/') ? path.substring(1) : path;
    final params = <String, String>{'route': route};
    if (query != null) {
      params.addAll(query);
    }
    return Uri.parse(baseUrl).replace(queryParameters: params);
  }

  static Future<ApiResponse> get(
    String path, {
    Map<String, String>? query,
    bool auth = false,
  }) async {
    try {
      final resp = await http
          .get(_uri(path, query), headers: await _headers(auth: auth))
          .timeout(const Duration(seconds: 20));
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
            _uri(path),
            headers: await _headers(auth: auth),
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
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
            _uri(path),
            headers: await _headers(auth: auth),
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
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
    try {
      final resp = await http
          .delete(_uri(path, query), headers: await _headers(auth: auth))
          .timeout(const Duration(seconds: 20));
      return ApiResponse.from(resp);
    } catch (e) {
      return ApiResponse.networkError(e.toString());
    }
  }
}

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
    final body = utf8.decode(resp.bodyBytes).trim();
    if (body.isEmpty) {
      return ApiResponse(
        ok: false,
        statusCode: resp.statusCode,
        error: 'Sunucu bos yanit dondu (HTTP ${resp.statusCode}).',
        code: 'EMPTY_BODY',
      );
    }
    try {
      final json = jsonDecode(body) as Map<String, dynamic>;
      return ApiResponse(
        ok: json['ok'] == true,
        statusCode: resp.statusCode,
        data: json['data'],
        error: json['error'] as String?,
        code: json['code'] as String?,
      );
    } catch (_) {
      return ApiResponse(
        ok: false,
        statusCode: resp.statusCode,
        error: 'Sunucu gecersiz yanit dondu.',
        code: 'INVALID_JSON',
      );
    }
  }

  factory ApiResponse.networkError(String message) {
    final lower = message.toLowerCase();
    String friendly;
    if (lower.contains('handshake') || lower.contains('certificate')) {
      friendly =
          'Guvenli baglanti kurulamadi. Uygulamayi guncelleyin veya internet baglantinizi kontrol edin.';
    } else if (lower.contains('timeout') || lower.contains('timed out')) {
      friendly = 'Sunucu yanit vermedi. Internet baglantinizi kontrol edin.';
    } else if (lower.contains('failed host lookup') ||
        lower.contains('socketexception')) {
      friendly = 'Sunucuya ulasilamadi. Internet baglantinizi kontrol edin.';
    } else {
      friendly = 'Baglanti hatasi: $message';
    }
    return ApiResponse(
      ok: false,
      statusCode: 0,
      error: friendly,
      code: 'NETWORK_ERROR',
    );
  }

  bool get isUnauthorized => statusCode == 401;
}
