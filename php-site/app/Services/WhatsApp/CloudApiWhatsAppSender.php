<?php

declare(strict_types=1);

namespace App\Services\WhatsApp;

/** Meta WhatsApp Cloud API — Authentication template. */
final class CloudApiWhatsAppSender implements WhatsAppSenderInterface
{
    /** @param array<string,mixed> $config */
    public function __construct(private array $config)
    {
    }

    public function isConfigured(): bool
    {
        return trim((string) ($this->config['access_token'] ?? '')) !== ''
            && trim((string) ($this->config['phone_number_id'] ?? '')) !== ''
            && trim((string) ($this->config['template_name'] ?? '')) !== '';
    }

    public function sendOtp(string $phoneE164, string $code): void
    {
        if (!$this->isConfigured()) {
            throw new \RuntimeException('WhatsApp API yapilandirilmamis.');
        }
        $to = preg_replace('/\D+/', '', $phoneE164) ?? '';
        if ($to === '') {
            throw new \RuntimeException('Gecersiz telefon numarasi.');
        }
        $version = (string) ($this->config['graph_version'] ?? 'v21.0');
        $phoneNumberId = (string) $this->config['phone_number_id'];
        $url = "https://graph.facebook.com/{$version}/{$phoneNumberId}/messages";
        $payload = [
            'messaging_product' => 'whatsapp',
            'to' => $to,
            'type' => 'template',
            'template' => [
                'name' => (string) $this->config['template_name'],
                'language' => ['code' => (string) ($this->config['template_language'] ?? 'tr')],
                'components' => [
                    [
                        'type' => 'body',
                        'parameters' => [
                            ['type' => 'text', 'text' => $code],
                        ],
                    ],
                    [
                        'type' => 'button',
                        'sub_type' => 'url',
                        'index' => '0',
                        'parameters' => [
                            ['type' => 'text', 'text' => $code],
                        ],
                    ],
                ],
            ],
        ];
        $json = json_encode($payload, JSON_UNESCAPED_UNICODE);
        if ($json === false) {
            throw new \RuntimeException('WhatsApp istegi olusturulamadi.');
        }
        $ctx = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => "Content-Type: application/json\r\nAuthorization: Bearer " . (string) $this->config['access_token'] . "\r\n",
                'content' => $json,
                'timeout' => 25,
                'ignore_errors' => true,
            ],
        ]);
        $resp = @file_get_contents($url, false, $ctx);
        if ($resp === false) {
            throw new \RuntimeException('WhatsApp API baglantisi basarisiz.');
        }
        $data = json_decode($resp, true);
        if (!is_array($data) || isset($data['error'])) {
            $msg = is_array($data['error'] ?? null) ? (string) ($data['error']['message'] ?? 'API hata') : 'API hata';
            throw new \RuntimeException('WhatsApp: ' . $msg);
        }
    }
}
