<?php

declare(strict_types=1);

namespace App\Services\Sms;

/** Netgsm HTTP API — canli SMS. */
final class NetgsmSmsSender implements SmsSenderInterface
{
    /** @param array<string,mixed> $config */
    public function __construct(private array $config)
    {
    }

    public function isConfigured(): bool
    {
        return trim((string) ($this->config['usercode'] ?? '')) !== ''
            && trim((string) ($this->config['password'] ?? '')) !== '';
    }

    public function sendOtp(string $phoneE164, string $code, string $message = ''): void
    {
        if (!$this->isConfigured()) {
            throw new \RuntimeException('Netgsm yapilandirilmamis.');
        }
        $msg = $message !== '' ? $message : ('BenimBazar dogrulama kodunuz: ' . $code);
        $gsm = preg_replace('/\D+/', '', $phoneE164) ?? '';
        if ($gsm === '') {
            throw new \RuntimeException('Gecersiz telefon numarasi.');
        }
        $params = [
            'usercode' => (string) $this->config['usercode'],
            'password' => (string) $this->config['password'],
            'gsmno' => $gsm,
            'message' => $msg,
            'msgheader' => (string) ($this->config['header'] ?? 'BENIMBAZAR'),
            'dil' => 'TR',
        ];
        $url = (string) ($this->config['api_url'] ?? 'https://api.netgsm.com.tr/sms/send/get/')
            . '?' . http_build_query($params);
        $ctx = stream_context_create(['http' => ['timeout' => 20, 'ignore_errors' => true]]);
        $resp = @file_get_contents($url, false, $ctx);
        if ($resp === false) {
            throw new \RuntimeException('Netgsm baglantisi basarisiz.');
        }
        $resp = trim($resp);
        if ($resp === '' || str_starts_with($resp, '20') || str_starts_with($resp, '30') || str_starts_with($resp, '40')) {
            throw new \RuntimeException('Netgsm hata: ' . $resp);
        }
    }
}
