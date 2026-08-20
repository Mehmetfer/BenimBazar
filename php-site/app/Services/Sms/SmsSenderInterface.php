<?php

declare(strict_types=1);

namespace App\Services\Sms;

/** SMS OTP gonderimi (Netgsm vb.). */
interface SmsSenderInterface
{
    /** @throws \RuntimeException */
    public function sendOtp(string $phoneE164, string $code, string $message = ''): void;

    public function isConfigured(): bool;
}
