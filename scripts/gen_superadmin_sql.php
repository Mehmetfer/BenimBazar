<?php
declare(strict_types=1);
/**
 * Canli superadmin sifresi icin SQL uretir (phpMyAdmin'de calistirin).
 * Kullanim: php scripts/gen_superadmin_sql.php "GucluSifre123!"
 */
require __DIR__ . '/../php-site/bootstrap.php';

$pass = $argv[1] ?? '';
if (strlen($pass) < 12) {
    fwrite(STDERR, "En az 12 karakter sifre verin.\n");
    fwrite(STDERR, "Ornek: php scripts/gen_superadmin_sql.php \"GucluSifre123!\"\n");
    exit(1);
}

$hash = App\Helpers\Auth::hashPassword($pass);
$sql = "UPDATE users SET password_hash = " . var_export($hash, true)
    . ", role = 'superadmin' WHERE username = 'superadmin';\n";

echo "-- Canli superadmin sifresi (deploy oncesi veya sonrasi phpMyAdmin'de calistirin)\n";
echo $sql;
