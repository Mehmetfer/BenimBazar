<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/UserAdminService.php';
require_once dirname(__DIR__) . '/app/Services/ExternalListingImportService.php';
require_once dirname(__DIR__) . '/app/Services/ImportSourceRegistry.php';
require_once dirname(__DIR__) . '/app/Services/ImportQueueService.php';

use App\Helpers\Security;
use App\Services\ImportQueueService;
use App\Services\ImportSourceRegistry;

cx_bootstrap();
$user = cx_require_staff();
if (!cx_is_admin($user) && !cx_is_superadmin($user)) {
    cx_flash('error', 'Import yalnizca admin/superadmin.');
    cx_redirect('/admin/');
}

$tabs = ImportSourceRegistry::tabs();
$queueSvc = new ImportQueueService();
$plan = $queueSvc->loadPlan();

$sourceKey = (string) ($_GET['source'] ?? $plan['source_key'] ?? 'kka');
if (!isset($tabs[$sourceKey])) {
    $sourceKey = 'kka';
}
$customDomain = trim((string) ($_GET['custom'] ?? $plan['custom_domain'] ?? ''));
$dateFrom = trim((string) ($_GET['date_from'] ?? $plan['date_from'] ?? '2026-06-01'));
$dateTo = trim((string) ($_GET['date_to'] ?? $plan['date_to'] ?? date('Y-m-d')));

try {
    $resolved = ImportSourceRegistry::resolve($sourceKey, $customDomain);
} catch (Throwable $e) {
    $resolved = ImportSourceRegistry::resolve('kka');
    cx_flash('error', $e->getMessage());
}

if ($dateFrom === '') {
    $dateFrom = (string) $resolved['default_date_from'];
}
if ($dateTo === '') {
    $dateTo = date('Y-m-d');
}

$analysis = $queueSvc->analyze(
    (string) $resolved['queue_dir'],
    (string) $resolved['domain'],
    $dateFrom,
    $dateTo
);

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    Security::rateLimit('ext_import', 30, 300);
    $action = (string) ($_POST['action'] ?? '');

    try {
        $postSource = (string) ($_POST['source_key'] ?? $sourceKey);
        $postCustom = trim((string) ($_POST['custom_domain'] ?? $customDomain));
        $postFrom = trim((string) ($_POST['date_from'] ?? $dateFrom));
        $postTo = trim((string) ($_POST['date_to'] ?? $dateTo));
        $resolvedPost = ImportSourceRegistry::resolve($postSource, $postCustom);

        if ($action === 'prepare') {
            $queueSvc->savePlan([
                'source_key' => $postSource,
                'custom_domain' => $postCustom,
                'date_from' => $postFrom,
                'date_to' => $postTo,
                'approved' => false,
            ], $user);
            cx_flash('ok', 'Aktarim plani hazirlandi: ' . $resolvedPost['label'] . ' · ' . $postFrom . ' — ' . $postTo);
        } elseif ($action === 'import_one') {
            if (empty($_POST['approve_import'])) {
                throw new RuntimeException('Tek ilan aktarmak icin onay kutusunu isaretleyin.');
            }
            $fresh = $queueSvc->analyze(
                (string) $resolvedPost['queue_dir'],
                (string) $resolvedPost['domain'],
                $postFrom,
                $postTo
            );
            if ($fresh['next'] === null) {
                throw new RuntimeException('Secilen aralikta bekleyen ilan yok.');
            }
            $result = (new \App\Services\ExternalListingImportService())->importOne($fresh['next']);
            cx_flash('ok', (string) $result['message']);
        } elseif ($action === 'import_batch') {
            if (empty($_POST['approve_import'])) {
                throw new RuntimeException('Toplu aktarim icin onay kutusunu isaretleyin.');
            }
            $limit = (int) ($_POST['batch_limit'] ?? 10);
            $results = $queueSvc->importBatch($resolvedPost, $postFrom, $postTo, $limit, $user);
            $ok = count(array_filter($results, static fn (array $r): bool => $r['ok']));
            $fail = count($results) - $ok;
            cx_flash('ok', $ok . ' ilan aktarildi' . ($fail > 0 ? ', ' . $fail . ' hata' : '') . '.');
        } else {
            throw new RuntimeException('Gecersiz islem.');
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }

    $qs = http_build_query(array_filter([
        'source' => $postSource ?? $sourceKey,
        'custom' => ($postCustom ?? $customDomain) !== '' ? ($postCustom ?? $customDomain) : null,
        'date_from' => $postFrom ?? $dateFrom,
        'date_to' => $postTo ?? $dateTo,
    ]));
    cx_redirect('/admin/import.php?' . $qs);
}

$queueExists = is_dir((string) $resolved['queue_dir']);
$meta = $analysis['meta'] ?? null;
$redirectQs = http_build_query(array_filter([
    'source' => $sourceKey,
    'custom' => $customDomain !== '' ? $customDomain : null,
    'date_from' => $dateFrom,
    'date_to' => $dateTo,
]));

ob_start();
$adminTab = 'import';
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>
<h1 class="admin-h1">Dis kaynak aktarim paneli</h1>
<p class="admin-lead">
  Kaynak site, tarih araligi ve onay adimlarini secin. Ilanlar <strong>ilan tarihine gore</strong> (eskiden yeniye) <?= cx_e(cx_site_name()) ?>'a aktarilir.
  Sterlin (£) korunur; satıcı hesaplari otomatik olusturulur.
</p>

<div class="share-card-format" style="margin-bottom:1rem">
  <?php foreach ($tabs as $key => $tab): ?>
    <?php
    $tabQs = http_build_query(array_filter([
        'source' => $key,
        'custom' => $key === 'custom' && $customDomain !== '' ? $customDomain : null,
        'date_from' => $dateFrom,
        'date_to' => $dateTo,
    ]));
    ?>
    <a class="<?= $sourceKey === $key ? 'is-active' : '' ?>" href="/admin/import.php?<?= cx_e($tabQs) ?>"><?= cx_e((string) $tab['label']) ?></a>
  <?php endforeach; ?>
</div>

<form method="post" class="admin-card" style="margin:1rem 0;padding:1rem;border:1px solid #2a3140;border-radius:12px">
  <?= cx_csrf_field() ?>
  <input type="hidden" name="action" value="prepare">
  <input type="hidden" name="source_key" value="<?= cx_e($sourceKey) ?>">

  <?php if ($sourceKey === 'custom'): ?>
    <p style="margin:0 0 .75rem">
      <label for="custom_domain"><strong>Site adi (domain)</strong></label><br>
      <input id="custom_domain" name="custom_domain" type="text" value="<?= cx_e($customDomain) ?>"
             placeholder="ornek.com" style="width:min(100%,320px);margin-top:.35rem;padding:.45rem .6rem">
      <br><span class="muted" style="font-size:.9rem">Kuyruk klasoru: <code>storage/import-queue/<?= cx_e(ImportSourceRegistry::domainSlug($customDomain !== '' ? $customDomain : 'site')) ?>/</code></span>
    </p>
  <?php else: ?>
    <input type="hidden" name="custom_domain" value="">
    <p class="muted" style="margin:0 0 .75rem"><?= cx_e((string) $resolved['hint']) ?></p>
  <?php endif; ?>

  <div style="display:flex;flex-wrap:wrap;gap:1rem;align-items:flex-end;margin-bottom:.75rem">
    <p style="margin:0">
      <label for="date_from"><strong>Baslangic tarihi</strong></label><br>
      <input id="date_from" name="date_from" type="date" value="<?= cx_e($dateFrom) ?>" style="margin-top:.35rem;padding:.45rem .6rem">
    </p>
    <p style="margin:0">
      <label for="date_to"><strong>Bitis tarihi</strong></label><br>
      <input id="date_to" name="date_to" type="date" value="<?= cx_e($dateTo) ?>" style="margin-top:.35rem;padding:.45rem .6rem">
    </p>
    <p style="margin:0">
      <button class="admin-btn admin-btn--primary" type="submit">Plani hazirla / onizle</button>
    </p>
  </div>

  <?php if ($meta): ?>
    <p class="muted" style="margin:0;font-size:.88rem">
      Son kuyruk olusturma: <?= cx_e((string) ($meta['built_at'] ?? '')) ?>
      <?php if (!empty($meta['cutoff'])): ?> · varsayilan kesim: <?= cx_e((string) $meta['cutoff']) ?><?php endif; ?>
      <?php if (!empty($meta['total'])): ?> · dosya: <?= (int) $meta['total'] ?><?php endif; ?>
    </p>
  <?php endif; ?>
</form>

<div class="admin-stats">
  <div class="admin-stat"><span class="admin-stat__n"><?= (int) $analysis['total'] ?></span><span class="admin-stat__l">Kuyruk (toplam)</span></div>
  <div class="admin-stat"><span class="admin-stat__n"><?= (int) $analysis['in_range'] ?></span><span class="admin-stat__l">Aralikta</span></div>
  <div class="admin-stat"><span class="admin-stat__n"><?= (int) $analysis['pending'] ?></span><span class="admin-stat__l">Bekleyen</span></div>
  <div class="admin-stat"><span class="admin-stat__n"><?= (int) $analysis['imported'] ?></span><span class="admin-stat__l">Zaten aktarildi</span></div>
  <div class="admin-stat"><span class="admin-stat__n"><?= (int) $analysis['out_of_range'] ?></span><span class="admin-stat__l">Aralik disi</span></div>
</div>

<?php if (!$queueExists): ?>
  <div class="admin-empty" style="margin-top:1rem">
    Kuyruk klasoru yok: <code><?= cx_e(str_replace(dirname(__DIR__) . '/', '', (string) $resolved['queue_dir'])) ?></code>
    <?php if ($resolved['script'] !== ''): ?>
      <br>PC'de kuyruk olustur: <code><?= cx_e((string) $resolved['script']) ?></code>
    <?php else: ?>
      <br>JSON ilan dosyalarini yukleyin veya PC'de o site icin kuyruk scripti calistirin.
    <?php endif; ?>
  </div>
<?php elseif ($analysis['pending'] === 0): ?>
  <div class="admin-empty" style="margin-top:1rem">
    Secilen tarih araliginda bekleyen ilan yok.
    <?php if ($analysis['imported'] > 0): ?> (<?= (int) $analysis['imported'] ?> zaten aktarilmis)<?php endif; ?>
  </div>
<?php else: ?>
  <?php if ($analysis['next']): $n = $analysis['next']; ?>
    <div class="admin-card" style="margin:1rem 0;padding:1rem;border:1px solid #2a3140;border-radius:12px">
      <h2 style="margin:0 0 .5rem;font-size:1.1rem">Siradaki ilan (onizleme)</h2>
      <p><strong><?= cx_e((string) ($n['title'] ?? '')) ?></strong></p>
      <p class="muted">
        <?= cx_e((string) ($n['source'] ?? $resolved['domain'])) ?> #<?= (int) ($n['source_id'] ?? 0) ?>
        · <?= cx_e((string) ($n['listed_at_iso'] ?? $n['listed_at'] ?? '')) ?>
      </p>
      <p><strong><?= cx_e((string) ($n['seller_name'] ?? '')) ?></strong>
        <?php if (!empty($n['seller_profile_line'])): ?>
          <br><span class="muted"><?= cx_e((string) $n['seller_profile_line']) ?></span>
        <?php endif; ?>
      </p>
      <?php if (!empty($n['price']) && is_array($n['price'])): ?>
        <p>Fiyat:
          <strong><?= number_format((float) ($n['price']['amount'] ?? 0), 0, ',', '.') ?>
            <?= cx_e((string) ($n['price']['currency'] ?? '')) ?></strong>
        </p>
      <?php endif; ?>
      <p>Foto: <?= count($n['photo_urls'] ?? []) ?> adet</p>
    </div>
  <?php endif; ?>

  <?php if ($analysis['preview'] !== []): ?>
    <div class="admin-card" style="margin:1rem 0;padding:0;border:1px solid #2a3140;border-radius:12px;overflow:auto">
      <table class="admin-table" style="width:100%;min-width:640px">
        <thead>
          <tr>
            <th>Tarih</th>
            <th>Baslik</th>
            <th>Kaynak #</th>
            <th>Fiyat</th>
            <th>Foto</th>
          </tr>
        </thead>
        <tbody>
          <?php foreach ($analysis['preview'] as $row): ?>
            <tr>
              <td><?= cx_e((string) ($row['listed_at_iso'] ?? $row['listed_at'] ?? '')) ?></td>
              <td><?= cx_e((string) ($row['title'] ?? '')) ?></td>
              <td>#<?= (int) ($row['source_id'] ?? 0) ?></td>
              <td>
                <?php if (!empty($row['price']) && is_array($row['price'])): ?>
                  <?= number_format((float) ($row['price']['amount'] ?? 0), 0, ',', '.') ?>
                  <?= cx_e((string) ($row['price']['currency'] ?? '')) ?>
                <?php else: ?>—<?php endif; ?>
              </td>
              <td><?= count($row['photo_urls'] ?? []) ?></td>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
      <?php if ($analysis['pending'] > count($analysis['preview'])): ?>
        <p class="muted" style="padding:.75rem 1rem;margin:0">+ <?= (int) ($analysis['pending'] - count($analysis['preview'])) ?> ilan daha (onizleme ilk 12)</p>
      <?php endif; ?>
    </div>
  <?php endif; ?>

  <form method="post" class="admin-card" style="margin:1rem 0;padding:1rem;border:1px solid #3d4a2a;border-radius:12px;background:#1a1f14">
    <?= cx_csrf_field() ?>
    <input type="hidden" name="source_key" value="<?= cx_e($sourceKey) ?>">
    <input type="hidden" name="custom_domain" value="<?= cx_e($customDomain) ?>">
    <input type="hidden" name="date_from" value="<?= cx_e($dateFrom) ?>">
    <input type="hidden" name="date_to" value="<?= cx_e($dateTo) ?>">

    <p style="margin:0 0 .75rem">
      <label style="display:flex;gap:.5rem;align-items:flex-start;cursor:pointer">
        <input type="checkbox" name="approve_import" value="1" required style="margin-top:.2rem">
        <span>
          <strong>Onayliyorum:</strong>
          <code><?= cx_e((string) $resolved['label']) ?></code> sitesinden
          <strong><?= cx_e($dateFrom) ?></strong> — <strong><?= cx_e($dateTo) ?></strong> araligindaki
          <strong><?= (int) $analysis['pending'] ?></strong> bekleyen ilani <?= cx_e(cx_site_name()) ?>'a aktarmak istiyorum.
        </span>
      </label>
    </p>

    <div style="display:flex;flex-wrap:wrap;gap:.75rem;align-items:center">
      <button class="admin-btn admin-btn--primary" type="submit" name="action" value="import_one">Tek ilan aktar (siradaki)</button>

      <label style="display:flex;align-items:center;gap:.35rem">
        <span>Toplu:</span>
        <select name="batch_limit" style="padding:.35rem .5rem">
          <?php foreach ([5, 10, 20, 50] as $n): ?>
            <option value="<?= $n ?>"<?= $n === 10 ? ' selected' : '' ?>><?= $n ?> ilan</option>
          <?php endforeach; ?>
        </select>
      </label>
      <button class="admin-btn admin-btn--primary" type="submit" name="action" value="import_batch">Onayla ve aktar</button>
    </div>
  </form>
<?php endif; ?>

<p class="admin-lead" style="margin-top:1.5rem">
  Kaynak: <strong><?= cx_e((string) $resolved['label']) ?></strong>
  · Kuyruk: <code><?= cx_e(str_replace(dirname(__DIR__) . DIRECTORY_SEPARATOR, '', (string) $resolved['queue_dir'])) ?></code>
  · Fotograflar: <code>uploads/ext-import/</code>
  <?php if ($resolved['script'] !== ''): ?>
    · Kuyruk guncelle: <code><?= cx_e((string) $resolved['script']) ?></code>
  <?php endif; ?>
</p>
<?php
$content = ob_get_clean();
$title = 'Import';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
