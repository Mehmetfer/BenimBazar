<?php

declare(strict_types=1);

namespace App\Services\WhatsApp;

/** Gelistirme / API yokken kodu loglar. */
final class DebugWhatsAppSender implements WhatsAppSenderInterface
{
    public function isConfigured(): bool
    {
        return true;
    }

    public function sendOtp(string $phoneE164, string $code): void
    {
        $line = date('c') . " WA DEBUG -> {$phoneE164} code={$code}\n";
        $path = dirname(__DIR__, 3) . '/storage/logs/phone-verify.log';
        @file_put_contents($path, $line, FILE_APPEND | LOCK_EX);
    }
}
