<?php

declare(strict_types=1);

namespace App\Services\WhatsApp;

/** WhatsApp Business Cloud API OTP. */
interface WhatsAppSenderInterface
{
    /** @throws \RuntimeException */
    public function sendOtp(string $phoneE164, string $code): void;

    public function isConfigured(): bool;
}
