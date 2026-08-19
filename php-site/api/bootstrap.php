<?php

/**
 * Mobil API bootstrap — Android / iOS için REST katmanı
 * Her API endpoint'i bu dosyayı require eder.
 */

declare(strict_types=1);

// Üst dizindeki uygulama bootstrap'ini yükle
require_once dirname(__DIR__) . '/bootstrap.php';

cx_bootstrap();

// CORS — mobil istemciler için (origin yok / cordova / capacitor)
$origin = $_SERVER['HTTP_ORIGIN'] ?? '*';
header('Access-Control-Allow-Origin: ' . $origin);
header('Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization, X-App-Version, X-Platform');
header('Access-Control-Max-Age: 86400');
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');

// OPTIONS preflight (tarayıcı / Capacitor CORS)
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

/**
 * Başarılı JSON yanıtı gönder ve çık.
 *
 * @param mixed $data
 */
function api_ok(mixed $data, int $status = 200): never
{
    http_response_code($status);
    echo json_encode(['ok' => true, 'data' => $data], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/**
 * Hata JSON yanıtı gönder ve çık.
 */
function api_error(string $message, int $status = 400, ?string $code = null): never
{
    http_response_code($status);
    $body = ['ok' => false, 'error' => $message];
    if ($code !== null) {
        $body['code'] = $code;
    }
    echo json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/**
 * Request body'den JSON parse et.
 *
 * @return array<string,mixed>
 */
function api_json_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) {
        return [];
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : [];
}

/**
 * Kimlik doğrulama — token yoksa 401 döner.
 *
 * @return array<string,mixed>
 */
function api_require_auth(): array
{
    $token = \App\Helpers\Auth::tokenFromRequest();
    if ($token === null) {
        api_error('Kimlik doğrulama gerekli.', 401, 'UNAUTHENTICATED');
    }
    $user = \App\Helpers\Auth::userFromToken($token);
    if ($user === null) {
        api_error('Oturum süresi dolmuş veya geçersiz.', 401, 'INVALID_TOKEN');
    }
    return $user;
}

/**
 * İzin verilen HTTP metodunu zorla.
 */
function api_method(string ...$allowed): void
{
    $method = strtoupper($_SERVER['REQUEST_METHOD']);
    if (!in_array($method, $allowed, true)) {
        header('Allow: ' . implode(', ', $allowed));
        api_error('Metod izin verilmiyor.', 405, 'METHOD_NOT_ALLOWED');
    }
}
