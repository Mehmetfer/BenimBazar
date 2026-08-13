import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../utils/url_utils.dart';

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
    final origin = safeOrigin();
    if (origin.isNotEmpty) return origin;
    // Last resort for non-http hosts (tests / unusual embeds).
    return Uri.base.toString().replaceAll(RegExp(r'/$'), '');
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

  Future<Map<String, dynamic>> getListing(int id) async {
    final res = await http.get(
      Uri.parse('$_root/api/listings/$id'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> updateListing(
    int id,
    Map<String, dynamic> body,
  ) async {
    final res = await http.patch(
      Uri.parse('$_root/api/listings/$id'),
      headers: await _headers(auth: true),
      body: jsonEncode(body),
    );
    return _decode(res);
  }

  /// Upload listing photo. Returns portable `/uploads/...` path (not absolute).
  Future<String> uploadImage({
    required List<int> bytes,
    required String filename,
    String contentType = 'image/jpeg',
  }) async {
    final uri = Uri.parse('$_root/api/uploads/image');
    final req = http.MultipartRequest('POST', uri);
    final token = await getToken();
    if (token != null) {
      req.headers['Authorization'] = 'Bearer $token';
    }
    req.files.add(
      http.MultipartFile.fromBytes(
        'file',
        bytes,
        filename: filename,
        contentType: MediaType.parse(contentType),
      ),
    );
    final streamed = await req.send();
    final res = await http.Response.fromStream(streamed);
    final data = _decode(res);
    // Prefer relative /uploads path so storage survives tunnel/host changes
    var url = data['url']?.toString() ?? '';
    if (url.isEmpty) {
      final abs = data['absolute_url']?.toString() ?? '';
      if (abs.contains('/uploads/')) {
        url = '/uploads/${abs.split('/uploads/').last}';
      }
    }
    if (url.isEmpty) {
      throw ApiException('Görsel yüklenemedi');
    }
    if (!url.startsWith('/')) {
      if (url.contains('/uploads/')) {
        url = '/uploads/${url.split('/uploads/').last}';
      } else {
        throw ApiException('Geçersiz görsel URL');
      }
    }
    return url;
  }

  Future<List<dynamic>> myListings() async {
    final res = await http.get(
      Uri.parse('$_root/api/listings/mine'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['listings'] as List?) ?? [];
  }

  /// Soft-delete listing (CANCELLED). Owner or admin/superadmin.
  Future<Map<String, dynamic>> cancelListing(int listingId) async {
    final res = await http.post(
      Uri.parse('$_root/api/listings/$listingId/cancel'),
      headers: await _headers(auth: true),
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

  Future<List<dynamic>> moderationQueue() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/moderation/queue'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['queue'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> moderationDecision(
    int listingId,
    String decision, {
    String reason = '',
  }) async {
    final res = await http.post(
      Uri.parse('$_root/api/admin/moderation/$listingId/decision'),
      headers: await _headers(auth: true),
      body: jsonEncode({'decision': decision, 'reason': reason}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> adminPanel() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/panel'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> adminDashboard() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/dashboard'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
  }

  Future<List<dynamic>> adminAudit({String actionPrefix = '', int limit = 50}) async {
    final qp = <String, String>{'limit': '$limit'};
    if (actionPrefix.isNotEmpty) qp['action_prefix'] = actionPrefix;
    final uri = Uri.parse('$_root/api/admin/audit').replace(queryParameters: qp);
    final res = await http.get(uri, headers: await _headers(auth: true));
    final data = _decode(res);
    return (data['audit'] as List?) ?? [];
  }

  Future<List<dynamic>> adminListings({
    String q = '',
    String owner = '',
    String status = '',
    String category = '',
  }) async {
    final qp = <String, String>{};
    if (q.isNotEmpty) qp['q'] = q;
    if (owner.isNotEmpty) qp['owner'] = owner;
    if (status.isNotEmpty) qp['status'] = status;
    if (category.isNotEmpty) qp['category'] = category;
    final uri = Uri.parse('$_root/api/admin/listings').replace(
      queryParameters: qp.isEmpty ? null : qp,
    );
    final res = await http.get(uri, headers: await _headers(auth: true));
    final data = _decode(res);
    return (data['listings'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> health() async {
    final res = await http.get(
      Uri.parse('$_root/api/health'),
      headers: await _headers(),
    );
    return _decode(res);
  }

  // --- Messaging / Support ---

  Future<int> messagesUnreadCount() async {
    final res = await http.get(
      Uri.parse('$_root/api/messages/unread-count'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['unread'] as num?)?.toInt() ?? 0;
  }

  Future<List<dynamic>> messagesInbox() async {
    final res = await http.get(
      Uri.parse('$_root/api/messages/inbox'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['conversations'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> startConversation(int listingId) async {
    final res = await http.post(
      Uri.parse('$_root/api/messages/conversations'),
      headers: await _headers(auth: true),
      body: jsonEncode({'listing_id': listingId}),
    );
    return _decode(res);
  }

  Future<List<dynamic>> conversationMessages(int conversationId) async {
    final res = await http.get(
      Uri.parse('$_root/api/messages/conversations/$conversationId/messages'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['messages'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> sendConversationMessage(
    int conversationId,
    String body, {
    bool acknowledgeContactWarning = false,
  }) async {
    final res = await http.post(
      Uri.parse('$_root/api/messages/conversations/$conversationId/messages'),
      headers: await _headers(auth: true),
      body: jsonEncode({
        'body': body,
        'acknowledge_contact_warning': acknowledgeContactWarning,
      }),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> reportMessage(int messageId, String reason) async {
    final res = await http.post(
      Uri.parse('$_root/api/messages/$messageId/report'),
      headers: await _headers(auth: true),
      body: jsonEncode({'reason': reason}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> blockUser(int userId) async {
    final res = await http.post(
      Uri.parse('$_root/api/messages/block'),
      headers: await _headers(auth: true),
      body: jsonEncode({'user_id': userId}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> createSupportTicket({
    required String subject,
    required String body,
    String category = 'GENERAL',
    String priority = 'NORMAL',
    String? attachmentUrl,
  }) async {
    final res = await http.post(
      Uri.parse('$_root/api/support/tickets'),
      headers: await _headers(auth: true),
      body: jsonEncode({
        'subject': subject,
        'body': body,
        'category': category,
        'priority': priority,
        if (attachmentUrl != null) 'attachment_url': attachmentUrl,
      }),
    );
    return _decode(res);
  }

  Future<List<dynamic>> mySupportTickets() async {
    final res = await http.get(
      Uri.parse('$_root/api/support/tickets'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['tickets'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> getSupportTicket(int id) async {
    final res = await http.get(
      Uri.parse('$_root/api/support/tickets/$id'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> replySupportTicket(int id, String body) async {
    final res = await http.post(
      Uri.parse('$_root/api/support/tickets/$id/messages'),
      headers: await _headers(auth: true),
      body: jsonEncode({'body': body}),
    );
    return _decode(res);
  }

  Future<List<dynamic>> adminSupportTickets() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/support/tickets'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['tickets'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> adminSupportReply(
    int ticketId,
    String body, {
    bool resolve = false,
  }) async {
    final res = await http.post(
      Uri.parse('$_root/api/admin/support/tickets/$ticketId/reply'),
      headers: await _headers(auth: true),
      body: jsonEncode({'body': body, 'resolve': resolve}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> adminSupportTicket(int ticketId) async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/support/tickets/$ticketId'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> adminModerateMessageReport(
    int reportId,
    String status,
  ) async {
    final res = await http.post(
      Uri.parse('$_root/api/admin/messages/reports/$reportId'),
      headers: await _headers(auth: true),
      body: jsonEncode({'status': status}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> softDeleteMessage(int messageId) async {
    final res = await http.delete(
      Uri.parse('$_root/api/messages/$messageId'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
  }

  Future<List<dynamic>> adminMessageReports() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/messages/reports'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['reports'] as List?) ?? [];
  }

  Future<List<dynamic>> adminStaff() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/staff'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['staff'] as List?) ?? [];
  }

  Future<List<dynamic>> adminUsers({String q = ''}) async {
    final uri = Uri.parse('$_root/api/admin/users').replace(
      queryParameters: q.isEmpty ? null : {'q': q},
    );
    final res = await http.get(uri, headers: await _headers(auth: true));
    final data = _decode(res);
    return (data['users'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> assignUserRole(
    int userId,
    String role, {
    String note = '',
  }) async {
    final res = await http.post(
      Uri.parse('$_root/api/admin/users/$userId/role'),
      headers: await _headers(auth: true),
      body: jsonEncode({'role': role, 'note': note}),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> createAssignment({
    required int listingId,
    required int assigneeId,
    String note = '',
  }) async {
    final res = await http.post(
      Uri.parse('$_root/api/admin/assignments'),
      headers: await _headers(auth: true),
      body: jsonEncode({
        'listing_id': listingId,
        'assignee_id': assigneeId,
        'note': note,
      }),
    );
    return _decode(res);
  }

  Future<List<dynamic>> myAssignments() async {
    final res = await http.get(
      Uri.parse('$_root/api/admin/assignments/mine'),
      headers: await _headers(auth: true),
    );
    final data = _decode(res);
    return (data['assignments'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> changeChainStatus() async {
    final res = await http.get(
      Uri.parse('$_root/api/change-chain/status'),
      headers: await _headers(auth: false),
    );
    return _decode(res);
  }

  Future<Map<String, dynamic>> matchingPreferences() async {
    final res = await http.get(
      Uri.parse('$_root/api/matching/preferences'),
      headers: await _headers(auth: true),
    );
    return _decode(res);
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
      String? code;
      Map<String, dynamic>? detailMap;
      if (detail is Map) {
        detailMap = Map<String, dynamic>.from(detail);
        message = detailMap['user_message']?.toString() ??
            detailMap['message']?.toString() ??
            detail.toString();
        code = detailMap['code']?.toString();
      } else {
        message = detail?.toString() ?? 'İstek başarısız (${res.statusCode})';
      }
      throw ApiException(
        message,
        statusCode: res.statusCode,
        code: code,
        detail: detailMap,
      );
    }
    return body;
  }
}

class ApiException implements Exception {
  ApiException(
    this.message, {
    this.statusCode,
    this.code,
    this.detail,
  });

  final String message;
  final int? statusCode;
  final String? code;
  final Map<String, dynamic>? detail;

  bool get isContactWarning =>
      code == 'CONTACT_INFO_WARNING' || statusCode == 409;

  bool get isContactBlocked => code == 'CONTACT_INFO_BLOCKED';

  @override
  String toString() => message;
}

final api = ChangeXApi();
