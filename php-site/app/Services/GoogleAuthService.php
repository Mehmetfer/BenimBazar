<?php



declare(strict_types=1);



namespace App\Services;



use App\Helpers\Database;



final class GoogleAuthService

{

    /** @return array<string,mixed> */

    public static function config(): array

    {

        $cfg = cx_app_config();

        $base = [

            'enabled' => false,

            'client_id' => '',

            'client_secret' => '',

            'redirect_uri' => rtrim((string) ($cfg['url'] ?? ''), '/') . '/auth/google-callback.php',

        ];

        $local = BASE_PATH . '/config/google.local.php';

        if (is_file($local)) {

            /** @var array<string,mixed> $over */

            $over = require $local;

            $base = array_merge($base, $over);

        }

        $base['enabled'] = ($base['client_id'] ?? '') !== '' && ($base['client_secret'] ?? '') !== '';

        return $base;

    }



    public static function authUrl(string $state): ?string

    {

        $c = self::config();

        if (!$c['enabled']) {

            return null;

        }

        $params = http_build_query([

            'client_id' => $c['client_id'],

            'redirect_uri' => $c['redirect_uri'],

            'response_type' => 'code',

            'scope' => 'openid email profile',

            'state' => $state,

            'access_type' => 'online',

            'prompt' => 'select_account',

        ]);

        return 'https://accounts.google.com/o/oauth2/v2/auth?' . $params;

    }



    /** @return array<string,mixed>|null */

    public static function exchangeCode(string $code): ?array

    {

        $c = self::config();

        if (!$c['enabled']) {

            return null;

        }

        $body = http_build_query([

            'code' => $code,

            'client_id' => $c['client_id'],

            'client_secret' => $c['client_secret'],

            'redirect_uri' => $c['redirect_uri'],

            'grant_type' => 'authorization_code',

        ]);

        $raw = self::httpRequest('POST', 'https://oauth2.googleapis.com/token', $body, [

            'Content-Type: application/x-www-form-urlencoded',

        ]);

        if ($raw === null) {

            return null;

        }

        $tok = json_decode($raw, true);

        if (!is_array($tok) || empty($tok['access_token'])) {

            return null;

        }

        $userRaw = self::httpRequest(

            'GET',

            'https://openidconnect.googleapis.com/v1/userinfo',

            null,

            ['Authorization: Bearer ' . $tok['access_token']]

        );

        if ($userRaw === null) {

            return null;

        }

        $user = json_decode($userRaw, true);

        return is_array($user) ? $user : null;

    }



    /** @param array<string,mixed> $profile */

    public static function loginOrRegister(array $profile): int

    {

        $googleId = (string) ($profile['sub'] ?? $profile['id'] ?? '');

        $email = trim((string) ($profile['email'] ?? ''));

        $name = (string) ($profile['name'] ?? 'google_user');

        $avatar = (string) ($profile['picture'] ?? '');

        $emailVerified = !empty($profile['email_verified']);

        if ($googleId === '') {

            throw new \RuntimeException('Google profil ID alinamadi');

        }

        if ($email === '' || !$emailVerified) {

            throw new \RuntimeException('Google hesabinizda dogrulanmis e-posta yok');

        }



        $pdo = Database::pdo();

        $stmt = $pdo->prepare('SELECT id, role, suspended, vip_starts_at, vip_ends_at FROM users WHERE google_id = ? LIMIT 1');

        $stmt->execute([$googleId]);

        $row = $stmt->fetch();

        if ($row) {

            if ((int) ($row['suspended'] ?? 0) === 1) {

                throw new \RuntimeException('Hesabiniz askiya alinmis.');

            }

            if (!cx_vip_can_login($row)) {

                throw new \RuntimeException(cx_vip_login_block_message($row));

            }

            self::touchGoogleProfile((int) $row['id'], $email, $avatar);

            return (int) $row['id'];

        }



        $emailStmt = $pdo->prepare('SELECT id, google_id, role, suspended, vip_starts_at, vip_ends_at FROM users WHERE email = ? LIMIT 1');

        $emailStmt->execute([$email]);

        $emailRow = $emailStmt->fetch();

        if ($emailRow) {

            if ((int) ($emailRow['suspended'] ?? 0) === 1) {

                throw new \RuntimeException('Hesabiniz askiya alinmis.');

            }

            if (!cx_vip_can_login($emailRow)) {

                throw new \RuntimeException(cx_vip_login_block_message($emailRow));

            }

            $uid = (int) $emailRow['id'];

            if (!empty($emailRow['google_id']) && (string) $emailRow['google_id'] !== $googleId) {

                throw new \RuntimeException('Bu e-posta baska bir Google hesabi ile bagli');

            }

            $pdo->prepare(

                'UPDATE users SET google_id = ?, avatar_url = COALESCE(NULLIF(?, \'\'), avatar_url), email = COALESCE(email, ?) WHERE id = ?'

            )->execute([$googleId, $avatar, $email, $uid]);

            return $uid;

        }



        $baseUser = preg_replace('/[^a-zA-Z0-9_]/', '', explode('@', $email)[0] ?? $name) ?: 'user';

        $username = mb_substr($baseUser, 0, 20);

        $n = 0;

        while (true) {

            $try = $n === 0 ? $username : $username . $n;

            $chk = $pdo->prepare('SELECT id FROM users WHERE username = ? LIMIT 1');

            $chk->execute([$try]);

            if (!$chk->fetch()) {

                $username = $try;

                break;

            }

            $n++;

        }

        $now = microtime(true);

        $country = 'tr';
        if (!empty($_SESSION['google_oauth_country'])) {
            $country = cx_normalize_country((string) $_SESSION['google_oauth_country']);
            unset($_SESSION['google_oauth_country']);
        }

        try {
            $pdo->prepare(
                'INSERT INTO users (username, password_hash, role, country, email, google_id, avatar_url, created_at)
                 VALUES (?,?,?,?,?,?,?,?)'
            )->execute([
                $username,
                \App\Helpers\Auth::hashPassword(bin2hex(random_bytes(16))),
                'user',
                $country,
                $email,
                $googleId,
                $avatar !== '' ? $avatar : null,
                $now,
            ]);
        } catch (\Throwable) {
            $pdo->prepare(
                'INSERT INTO users (username, password_hash, role, email, google_id, avatar_url, created_at)
                 VALUES (?,?,?,?,?,?,?)'
            )->execute([
                $username,
                \App\Helpers\Auth::hashPassword(bin2hex(random_bytes(16))),
                'user',
                $email,
                $googleId,
                $avatar !== '' ? $avatar : null,
                $now,
            ]);
        }

        return (int) $pdo->lastInsertId();

    }



    private static function touchGoogleProfile(int $userId, string $email, string $avatar): void

    {

        Database::pdo()->prepare(

            'UPDATE users SET email = COALESCE(email, ?), avatar_url = COALESCE(NULLIF(?, \'\'), avatar_url) WHERE id = ?'

        )->execute([$email, $avatar, $userId]);

    }



    private static function httpRequest(string $method, string $url, ?string $body = null, array $headers = []): ?string

    {

        if (function_exists('curl_init')) {

            $ch = curl_init($url);

            if ($ch === false) {

                return null;

            }

            curl_setopt_array($ch, [

                CURLOPT_RETURNTRANSFER => true,

                CURLOPT_TIMEOUT => 15,

                CURLOPT_CUSTOMREQUEST => strtoupper($method),

                CURLOPT_HTTPHEADER => $headers,

            ]);

            if ($body !== null) {

                curl_setopt($ch, CURLOPT_POSTFIELDS, $body);

            }

            $raw = curl_exec($ch);

            curl_close($ch);

            return is_string($raw) ? $raw : null;

        }



        $headerLine = $headers !== [] ? implode("\r\n", $headers) . "\r\n" : '';

        $ctx = stream_context_create([

            'http' => [

                'method' => strtoupper($method),

                'header' => $headerLine,

                'content' => $body ?? '',

                'timeout' => 15,

                'ignore_errors' => true,

            ],

        ]);

        $raw = @file_get_contents($url, false, $ctx);

        return is_string($raw) ? $raw : null;

    }

}

