<?php

/**
 * POST /api/v1/auth/logout
 * Header: Authorization: Bearer <token>
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Auth;

api_method('POST');

$token = Auth::tokenFromRequest();
if ($token !== null) {
    Auth::revokeSession($token);
}

api_ok(['message' => 'Cikis yapildi.']);
