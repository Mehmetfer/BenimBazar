<?php

declare(strict_types=1);

namespace App\Services\Sms;

/** Gelistirme / provider yokken kodu loglar. */
final class DebugSmsSender implements SmsSenderInterface
{
    public function isConfigured(): bool
    {
        return true;
    }

    public function sendOtp(string $phoneE164, string $code, string $message = ''): void
    {
        $line = date('c') . " SMS DEBUG -> {$phoneE164} code={$code}\n";
        $path = dirname(__DIR__, 3) . '/storage/logs/phone-verify.log';
        @file_put_contents($path, $line, FILE_APPEND | LOCK_EX);
    }
}
