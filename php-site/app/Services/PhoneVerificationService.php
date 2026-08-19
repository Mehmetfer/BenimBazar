<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use App\Services\Sms\DebugSmsSender;
use App\Services\Sms\NetgsmSmsSender;
use App\Services\Sms\SmsSenderInterface;
use App\Services\WhatsApp\CloudApiWhatsAppSender;
use App\Services\WhatsApp\DebugWhatsAppSender;
use App\Services\WhatsApp\WhatsAppSenderInterface;
use PDO;
use RuntimeException;

/** Telefon OTP — SMS + WhatsApp kanallari, debug mod destekli. */
final class PhoneVerificationService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
        self::ensureSchema();
    }

    public static function ensureSchema(): void
    {
        try {
            ListingSchemaService::ensureUserProfileColumns(Database::pdo());
            $pdo = Database::pdo();
            if (!self::columnExists($pdo, 'users', 'phone_verified_at')) {
                try {
                    $pdo->exec('ALTER TABLE users ADD COLUMN phone_verified_at DOUBLE NULL DEFAULT NULL AFTER phone');
                } catch (\Throwable) {
                    // migrate-v6
                }
            }
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS phone_verifications (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  user_id INT UNSIGNED NOT NULL,
                  phone VARCHAR(32) NOT NULL,
                  phone_key VARCHAR(16) NOT NULL,
                  code_hash VARCHAR(255) NOT NULL,
                  channel VARCHAR(16) NOT NULL DEFAULT \'debug\',
                  attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
                  sent_at DOUBLE NOT NULL,
                  expires_at DOUBLE NOT NULL,
                  verified_at DOUBLE NULL,
                  PRIMARY KEY (id),
                  KEY idx_pv_user_sent (user_id, sent_at),
                  KEY idx_pv_phone_key (phone_key)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
            );
        } catch (\Throwable) {
            // yetki / eski MySQL
        }
    }

    public static function isVerifiedUser(?array $user): bool
    {
        if ($user === null) {
            return false;
        }

        return ((float) ($user['phone_verified_at'] ?? 0)) > 0;
    }

    /** @return array{ok:bool,debug_code?:string,expires_minutes:int,channel:string} */
    public function sendCode(int $userId, string $phone, string $channel): array
    {
        if ($userId <= 0) {
            throw new RuntimeException('Oturum gerekli.');
        }
        $phone = $this->normalizeDisplayPhone($phone);
        $this->assertValidPhone($phone);
        $phoneKey = cx_phone_match_key($phone);
        if ($phoneKey === '') {
            throw new RuntimeException('Gecersiz telefon numarasi.');
        }
        if ($this->phoneKeyUsedByOther($phoneKey, $userId)) {
            throw new RuntimeException('Bu telefon numarasi baska bir hesapta kayitli.');
        }

        $this->assertSendRateLimit($userId);

        $cfg = cx_phone_verify_settings();
        $ttl = max(60, (int) ($cfg['code_ttl_seconds'] ?? 300));
        $code = $this->generateCode();
        $now = microtime(true);
        $channel = $this->normalizeChannel($channel);

        $this->pdo->prepare(
            'INSERT INTO phone_verifications (user_id, phone, phone_key, code_hash, channel, sent_at, expires_at)
             VALUES (?,?,?,?,?,?,?)'
        )->execute([
            $userId,
            $phone,
            $phoneKey,
            password_hash($code, PASSWORD_DEFAULT),
            $channel,
            $now,
            $now + $ttl,
        ]);

        $this->updateUserPhone($userId, $phone);

        $debugCode = null;
        $deliveredChannel = $this->deliverCode($phone, $code, $channel, $debugCode);

        return [
            'ok' => true,
            'debug_code' => $debugCode,
            'expires_minutes' => (int) ceil($ttl / 60),
            'channel' => $deliveredChannel,
        ];
    }

    public function confirmCode(int $userId, string $code): bool
    {
        if ($userId <= 0) {
            throw new RuntimeException('Oturum gerekli.');
        }
        $code = preg_replace('/\D+/', '', trim($code)) ?? '';
        if (strlen($code) < 4 || strlen($code) > 8) {
            throw new RuntimeException('Gecersiz kod formati.');
        }

        $row = $this->latestPending($userId);
        if ($row === null) {
            throw new RuntimeException('Aktif dogrulama kodu yok. Yeni kod isteyin.');
        }

        $maxAttempts = max(3, (int) (cx_phone_verify_settings()['max_attempts'] ?? 5));
        if ((int) ($row['attempts'] ?? 0) >= $maxAttempts) {
            throw new RuntimeException('Cok fazla hatali deneme. Yeni kod isteyin.');
        }
        if ((float) ($row['expires_at'] ?? 0) < microtime(true)) {
            throw new RuntimeException('Kodun suresi doldu. Yeni kod isteyin.');
        }

        $this->pdo->prepare('UPDATE phone_verifications SET attempts = attempts + 1 WHERE id = ?')
            ->execute([(int) $row['id']]);

        if (!password_verify($code, (string) ($row['code_hash'] ?? ''))) {
            throw new RuntimeException('Dogrulama kodu hatali.');
        }

        $phoneKey = (string) ($row['phone_key'] ?? '');
        if ($phoneKey !== '' && $this->phoneKeyUsedByOther($phoneKey, $userId)) {
            throw new RuntimeException('Bu telefon numarasi baska bir hesapta dogrulanmis.');
        }

        $now = microtime(true);
        $this->pdo->beginTransaction();
        try {
            $this->pdo->prepare(
                'UPDATE phone_verifications SET verified_at = ? WHERE id = ?'
            )->execute([$now, (int) $row['id']]);
            $this->pdo->prepare(
                'UPDATE users SET phone = ?, phone_verified_at = ? WHERE id = ?'
            )->execute([(string) ($row['phone'] ?? ''), $now, $userId]);
            $this->pdo->commit();
        } catch (\Throwable $e) {
            $this->pdo->rollBack();
            throw $e;
        }

        return true;
    }

    /** @return array<string,mixed>|null */
    public function latestPending(int $userId): ?array
    {
        try {
            $stmt = $this->pdo->prepare(
                'SELECT * FROM phone_verifications
                 WHERE user_id = ? AND verified_at IS NULL
                 ORDER BY id DESC LIMIT 1'
            );
            $stmt->execute([$userId]);
            $row = $stmt->fetch();

            return is_array($row) ? $row : null;
        } catch (\Throwable) {
            return null;
        }
    }

    private function deliverCode(string $phone, string $code, string $channel, ?string &$debugCode): string
    {
        $cfg = cx_phone_verify_settings();
        $mode = strtolower(trim((string) ($cfg['mode'] ?? 'debug')));
        $useDebug = $mode === 'debug';

        if ($channel === 'whatsapp') {
            $sender = $this->whatsappSender();
            if (!$useDebug && $sender->isConfigured()) {
                try {
                    $sender->sendOtp($this->toE164($phone), $code);
                    return 'whatsapp';
                } catch (\Throwable) {
                    // SMS yedek
                }
            }
            (new DebugWhatsAppSender())->sendOtp($this->toE164($phone), $code);
            $debugCode = $code;

            return 'debug_whatsapp';
        }

        $sms = $this->smsSender();
        if (!$useDebug && $sms->isConfigured()) {
            try {
                $sms->sendOtp($this->toE164($phone), $code);
                return 'sms';
            } catch (\Throwable) {
                // asagida debug
            }
        }
        (new DebugSmsSender())->sendOtp($this->toE164($phone), $code);
        $debugCode = $code;

        return 'debug_sms';
    }

    private function whatsappSender(): WhatsAppSenderInterface
    {
        return new CloudApiWhatsAppSender(cx_whatsapp_config());
    }

    private function smsSender(): SmsSenderInterface
    {
        return new NetgsmSmsSender(cx_sms_config());
    }

    private function generateCode(): string
    {
        return str_pad((string) random_int(0, 999999), 6, '0', STR_PAD_LEFT);
    }

    private function normalizeChannel(string $channel): string
    {
        $channel = strtolower(trim($channel));

        return in_array($channel, ['whatsapp', 'sms'], true) ? $channel : 'whatsapp';
    }

    private function normalizeDisplayPhone(string $phone): string
    {
        return trim(preg_replace('/\s+/u', ' ', $phone) ?? '');
    }

    private function assertValidPhone(string $phone): void
    {
        $digits = cx_phone_digits($phone);
        if (strlen($digits) < 10) {
            throw new RuntimeException('Gecerli bir GSM numarasi girin.');
        }
    }

    private function toE164(string $phone): string
    {
        $digits = cx_phone_digits($phone);
        if (str_starts_with($digits, '90') && strlen($digits) >= 12) {
            return '+' . $digits;
        }
        if (str_starts_with($digits, '0')) {
            return '+90' . substr($digits, 1);
        }
        if (strlen($digits) === 10) {
            return '+90' . $digits;
        }

        return '+' . $digits;
    }

    private function updateUserPhone(int $userId, string $phone): void
    {
        $this->pdo->prepare('UPDATE users SET phone = ? WHERE id = ?')->execute([$phone, $userId]);
    }

    private function phoneKeyUsedByOther(string $phoneKey, int $userId): bool
    {
        if ($phoneKey === '') {
            return false;
        }
        try {
            $stmt = $this->pdo->query(
                'SELECT id, phone FROM users WHERE phone_verified_at IS NOT NULL AND phone_verified_at > 0'
            );
            if (!$stmt) {
                return false;
            }
            while ($row = $stmt->fetch()) {
                if ((int) ($row['id'] ?? 0) === $userId) {
                    continue;
                }
                if (cx_phone_match_key((string) ($row['phone'] ?? '')) === $phoneKey) {
                    return true;
                }
            }
        } catch (\Throwable) {
            return false;
        }

        return false;
    }

    private function assertSendRateLimit(int $userId): void
    {
        $max = max(1, (int) (cx_phone_verify_settings()['max_send_per_hour'] ?? 5));
        $since = microtime(true) - 3600;
        try {
            $stmt = $this->pdo->prepare(
                'SELECT COUNT(*) FROM phone_verifications WHERE user_id = ? AND sent_at >= ?'
            );
            $stmt->execute([$userId, $since]);
            if ((int) $stmt->fetchColumn() >= $max) {
                throw new RuntimeException('Saatlik kod gonderim limitine ulastiniz. Lutfen bekleyin.');
            }
        } catch (RuntimeException $e) {
            throw $e;
        } catch (\Throwable) {
            // tablo yoksa atla
        }
    }

    private static function columnExists(PDO $pdo, string $table, string $column): bool
    {
        $table = preg_replace('/[^a-zA-Z0-9_]/', '', $table) ?? '';
        $column = preg_replace('/[^a-zA-Z0-9_]/', '', $column) ?? '';
        if ($table === '' || $column === '') {
            return false;
        }
        try {
            $sql = 'SHOW COLUMNS FROM `' . $table . '` LIKE ' . $pdo->quote($column);
            $stmt = $pdo->query($sql);

            return (bool) ($stmt && $stmt->fetch());
        } catch (\Throwable) {
            return false;
        }
    }
}
