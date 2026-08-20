<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

use App\Helpers\Auth;

cx_bootstrap();
$token = Auth::tokenFromRequest();
Auth::revokeSession($token);
Auth::clearTokenCookie();
cx_redirect('/');
