<?php

declare(strict_types=1);

/** KKTC şehirleri ve konum eşleme anahtar kelimeleri. */
function cx_kktc_cities(): array
{
    return [
        'girne' => [
            'label' => 'Girne',
            'needles' => [
                'girne', 'kyrenia', 'alsancak', 'lapta', 'çatalköy', 'catalkoy',
                'karaoğlanoğlu', 'karaoglanoglu', 'bellapais', 'karakum',
            ],
        ],
        'magusa' => [
            'label' => 'Mağusa',
            'needles' => [
                'magosa', 'mağusa', 'magusa', 'famagusta', 'gazimağusa', 'gazimagusa',
                'salamis', 'tuzla', 'mutluyaka',
            ],
        ],
        'lefkosa' => [
            'label' => 'Lefkoşa',
            'needles' => [
                'lefkoşa', 'lefkosa', 'nicosia', 'gönyeli', 'gonyeli', 'hamitköy', 'hamitkoy',
                'haspolat', 'değirmenlik', 'degirmenlik',
            ],
        ],
        'guzelyurt' => [
            'label' => 'Güzelyurt',
            'needles' => [
                'güzelyurt', 'guzelyurt', 'morphou', 'gemikonağı', 'gemikonagi',
            ],
        ],
        'iskele' => [
            'label' => 'İskele',
            'needles' => [
                'iskele', 'karpaz', 'dipkarpaz', 'bafra', 'long beach', 'mehmetçik', 'mehmetcik',
            ],
        ],
    ];
}

function cx_kktc_city_valid(string $code): bool
{
    $code = strtolower(trim($code));

    return $code !== '' && isset(cx_kktc_cities()[$code]);
}

function cx_kktc_city_label(string $code): string
{
    $code = strtolower(trim($code));
    $cities = cx_kktc_cities();

    return $cities[$code]['label'] ?? '';
}

/** @return list<string> */
function cx_kktc_city_needles(string $code): array
{
    $code = strtolower(trim($code));
    $cities = cx_kktc_cities();

    return $cities[$code]['needles'] ?? [];
}
