<?php



declare(strict_types=1);



namespace App\Services;



use App\Helpers\Database;

use PDO;



require_once __DIR__ . '/SocialService.php';



final class ListingService

{

    private PDO $pdo;

    private int $listingNoBase;

    private int $feedLimit;



    public function __construct(int $listingNoBase = 1000000000)

    {

        $this->pdo = Database::pdo();

        $this->listingNoBase = $listingNoBase;

        $this->feedLimit = max(20, min(200, (int) (cx_app_config()['feed_limit'] ?? 120)));

    }



    /** @return list<array<string,mixed>> */

    public function publicFeed(

        ?string $q = null,

        ?int $viewerId = null,

        ?string $category = null,

        ?string $subcatSlug = null,

        bool $includeSold = false,

        string $region = '',
        string $kktcCity = '',
        string $sort = 'new'

    ): array {

        $sql = "SELECT l.*, u.username AS owner_username

                FROM trade_listings l

                JOIN users u ON u.id = l.owner_id

                WHERE " . $this->feedStatusSql($includeSold);

        $args = [];



        $subEntry = ($subcatSlug !== null && $subcatSlug !== '') ? cx_marketplace_by_slug($subcatSlug) : null;

        if ($subEntry !== null) {

            $sql .= ' AND l.subcategory = ?';

            $args[] = $subEntry['label'];

        } elseif ($category !== null && $category !== '' && !cx_meta_category($category)) {

            $sql .= ' AND l.category = ?';

            $args[] = $category;

        }

        if ($q !== null && $q !== '') {

            $lid = cx_parse_listing_no($q, $this->listingNoBase);

            if ($lid !== null) {

                $sql .= ' AND l.id = ?';

                $args[] = $lid;

            } else {

                $sql .= ' AND (l.title LIKE ? OR l.description LIKE ? OR l.wanted_items LIKE ?
                    OR COALESCE(u.username, \'\') LIKE ?)';

                $like = '%' . $q . '%';

                $args[] = $like;

                $args[] = $like;

                $args[] = $like;

                $args[] = $like;

            }

        }

        [$regionSql, $regionArgs] = cx_region_sql($region, 'l', $kktcCity);
        $sql .= $regionSql;
        foreach ($regionArgs as $ra) {
            $args[] = $ra;
        }

        [$qualitySql, $qualityArgs] = $this->feedQualitySql($subEntry !== null);
        $sql .= $qualitySql;
        foreach ($qualityArgs as $qa) {
            $args[] = $qa;
        }

        $fetchLimit = cx_listing_sort_needs_expanded_fetch($sort)
            ? min(200, $this->feedLimit * 2)
            : $this->feedLimit;

        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . $fetchLimit;

        $stmt = $this->pdo->prepare($sql);

        $stmt->execute($args);

        $rows = $stmt->fetchAll();

        $rows = $this->filterFeedQualityRows($rows);

        $rows = $this->enrichMany($rows, $viewerId);

        if (cx_listing_sort_needs_php($sort)) {
            $rows = cx_listing_sort_items($rows, $sort);
            $rows = array_slice($rows, 0, $this->feedLimit);
        }

        return $rows;

    }



    /**

     * @param array<string,mixed> $filters

     * @return list<array<string,mixed>>

     */

    public function vehicleBrowseFeed(?string $q, ?int $viewerId, string $veh, array $filters, bool $includeSold = false, string $region = '', string $kktcCity = '', string $sort = 'new'): array

    {

        $seg = cx_vehicle_segments()[$veh] ?? null;

        if ($seg === null) {

            return [];

        }



        $sql = "SELECT l.*, u.username AS owner_username

                FROM trade_listings l

                JOIN users u ON u.id = l.owner_id

                WHERE " . $this->feedStatusSql($includeSold);

        $args = [];



        $catPlaceholders = implode(',', array_fill(0, count($seg['categories']), '?'));

        $sql .= " AND l.category IN ($catPlaceholders)";

        foreach ($seg['categories'] as $c) {

            $args[] = $c;

        }



        if ($q !== null && $q !== '') {

            $lid = cx_parse_listing_no($q, $this->listingNoBase);

            if ($lid !== null) {

                $sql .= ' AND l.id = ?';

                $args[] = $lid;

            } else {

                $sql .= ' AND (l.title LIKE ? OR l.description LIKE ? OR l.wanted_items LIKE ?
                    OR COALESCE(u.username, \'\') LIKE ?)';

                $like = '%' . $q . '%';

                $args[] = $like;

                $args[] = $like;

                $args[] = $like;

                $args[] = $like;

            }

        }

        [$regionSql, $regionArgs] = cx_region_sql($region, 'l', $kktcCity);
        $sql .= $regionSql;
        foreach ($regionArgs as $ra) {
            $args[] = $ra;
        }

        [$qualitySql, $qualityArgs] = $this->feedQualitySql(true);
        $sql .= $qualitySql;
        foreach ($qualityArgs as $qa) {
            $args[] = $qa;
        }

        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . min(200, $this->feedLimit * 2);

        $stmt = $this->pdo->prepare($sql);

        $stmt->execute($args);

        $rows = $stmt->fetchAll();

        $rows = $this->filterFeedQualityRows($rows);

        $out = [];

        foreach ($this->enrichMany($rows, $viewerId) as $item) {

            if (!cx_listing_matches_vehicle_segment($item, $veh)) {

                continue;

            }

            if (!cx_listing_matches_vehicle_filters($item, $filters, $veh)) {

                continue;

            }

            $out[] = $item;

        }

        if (cx_listing_sort_needs_php($sort)) {
            $out = cx_listing_sort_items($out, $sort);
        }

        return array_slice($out, 0, $this->feedLimit);

    }



    /** @return array<string,int> */

    public function vehicleBrandCounts(string $veh, ?string $commercialType = null, string $region = '', string $kktcCity = ''): array

    {

        $seg = cx_vehicle_segments()[$veh] ?? null;

        if ($seg === null) {

            return [];

        }



        $sql = "SELECT l.*, u.username AS owner_username

                FROM trade_listings l

                JOIN users u ON u.id = l.owner_id

                WHERE UPPER(l.status) IN ('APPROVED','ACTIVE')";

        $args = [];



        $catPlaceholders = implode(',', array_fill(0, count($seg['categories']), '?'));

        $sql .= " AND l.category IN ($catPlaceholders)";

        foreach ($seg['categories'] as $c) {

            $args[] = $c;

        }

        [$regionSql, $regionArgs] = cx_region_sql($region, 'l', $kktcCity);
        $sql .= $regionSql;
        foreach ($regionArgs as $ra) {
            $args[] = $ra;
        }

        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . min(200, $this->feedLimit * 2);

        $stmt = $this->pdo->prepare($sql);

        $stmt->execute($args);



        $counts = [];

        foreach ($stmt->fetchAll() as $row) {

            $item = $this->lightItem($row);

            if (!cx_listing_matches_vehicle_segment($item, $veh)) {

                continue;

            }

            if ($commercialType !== null && cx_vehicle_commercial_type_valid($commercialType)) {

                if (cx_listing_commercial_type($item) !== $commercialType) {

                    continue;

                }

            }

            $make = cx_listing_vehicle_make($item, $veh);

            if ($make === '') {

                continue;

            }

            $counts[$make] = ($counts[$make] ?? 0) + 1;

        }



        return $counts;

    }



    /** @return array<string,int> */

    public function vehicleModelCounts(string $veh, string $make, ?string $commercialType = null): array

    {

        $seg = cx_vehicle_segments()[$veh] ?? null;

        if ($seg === null) {

            return [];

        }



        $make = cx_vehicle_canonical_make($make, $veh);

        $sql = "SELECT l.*, u.username AS owner_username

                FROM trade_listings l

                JOIN users u ON u.id = l.owner_id

                WHERE UPPER(l.status) IN ('APPROVED','ACTIVE')";

        $args = [];



        $catPlaceholders = implode(',', array_fill(0, count($seg['categories']), '?'));

        $sql .= " AND l.category IN ($catPlaceholders)";

        foreach ($seg['categories'] as $c) {

            $args[] = $c;

        }



        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . $this->feedLimit;

        $stmt = $this->pdo->prepare($sql);

        $stmt->execute($args);



        $counts = [];

        foreach ($stmt->fetchAll() as $row) {

            $item = $this->lightItem($row);

            if (!cx_listing_matches_vehicle_segment($item, $veh)) {

                continue;

            }

            if ($commercialType !== null && cx_vehicle_commercial_type_valid($commercialType)) {

                if (cx_listing_commercial_type($item) !== $commercialType) {

                    continue;

                }

            }

            $listingMake = cx_listing_vehicle_make($item, $veh);

            if (!cx_vehicle_make_equals($make, $listingMake, $veh)) {

                continue;

            }

            $model = cx_listing_vehicle_model($item, $veh, $make);

            if ($model === '') {

                continue;

            }

            $counts[$model] = ($counts[$model] ?? 0) + 1;

        }



        return $counts;

    }



    /** @return array<string,int> */

    public function vehicleCommercialTypeCounts(): array

    {

        $veh = 'ticari';

        $seg = cx_vehicle_segments()[$veh] ?? null;

        if ($seg === null) {

            return [];

        }



        $sql = "SELECT l.*, u.username AS owner_username

                FROM trade_listings l

                JOIN users u ON u.id = l.owner_id

                WHERE UPPER(l.status) IN ('APPROVED','ACTIVE')";

        $args = [];



        $catPlaceholders = implode(',', array_fill(0, count($seg['categories']), '?'));

        $sql .= " AND l.category IN ($catPlaceholders)";

        foreach ($seg['categories'] as $c) {

            $args[] = $c;

        }



        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . $this->feedLimit;

        $stmt = $this->pdo->prepare($sql);

        $stmt->execute($args);



        $counts = [];

        foreach (cx_vehicle_commercial_types() as $id => $_row) {

            $counts[$id] = 0;

        }



        foreach ($stmt->fetchAll() as $row) {

            $item = $this->lightItem($row);

            if (!cx_listing_matches_vehicle_segment($item, $veh)) {

                continue;

            }

            $type = cx_listing_commercial_type($item);

            $counts[$type] = ($counts[$type] ?? 0) + 1;

        }



        return $counts;

    }



    /** @return list<array<string,mixed>> */
    public function findSimilarPublic(array $item, ?int $viewerId, ?int $limit = null): array
    {
        if (!cx_similar_listings_enabled()) {
            return [];
        }

        $cfg = cx_similar_listings_settings();
        $limit = $limit ?? $cfg['limit'];
        $attrs = cx_listing_attrs($item);
        $attrs['_title'] = (string) ($item['title'] ?? '');
        $excludeId = (int) ($item['id'] ?? 0);
        $matches = cx_listing_find_similar_public($attrs, $excludeId, $limit);
        if ($matches === []) {
            return [];
        }

        $ids = [];
        foreach ($matches as $match) {
            $ids[] = (int) ($match['id'] ?? 0);
        }
        $ids = array_values(array_filter($ids, static fn (int $v): bool => $v > 0));
        if ($ids === []) {
            return [];
        }

        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $stmt = $this->pdo->prepare(
            "SELECT l.*, u.username AS owner_username
             FROM trade_listings l
             JOIN users u ON u.id = l.owner_id
             WHERE l.id IN ($placeholders)"
        );
        $stmt->execute($ids);

        $rowsById = [];
        foreach ($stmt->fetchAll() ?: [] as $row) {
            if (is_array($row)) {
                $rowsById[(int) $row['id']] = $row;
            }
        }

        $ordered = [];
        foreach ($ids as $lid) {
            if (isset($rowsById[$lid])) {
                $ordered[] = $rowsById[$lid];
            }
        }

        return $this->enrichRows($ordered, $viewerId);
    }



    /** @return array<string,mixed>|null */

    public function findById(int $id, ?int $viewerId = null): ?array

    {

        try {
            $stmt = $this->pdo->prepare(
                'SELECT l.*, u.username AS owner_username, u.role AS owner_role,
                        u.avatar_url AS owner_avatar_url, u.change_score, u.phone_verified_at AS owner_phone_verified_at
                 FROM trade_listings l JOIN users u ON u.id = l.owner_id WHERE l.id = ?'
            );
            $stmt->execute([$id]);
            $row = $stmt->fetch();
        } catch (\Throwable) {
            $stmt = $this->pdo->prepare(
                'SELECT l.*, u.username AS owner_username, u.change_score
                 FROM trade_listings l JOIN users u ON u.id = l.owner_id WHERE l.id = ?'
            );
            $stmt->execute([$id]);
            $row = $stmt->fetch();
        }

        return $row ? $this->enrich($row, $viewerId, true) : null;

    }



    /** @param list<array<string,mixed>> $rows @return list<array<string,mixed>> */
    public function enrichRows(array $rows, ?int $viewerId): array
    {
        return $this->enrichMany($rows, $viewerId);
    }

    /** @param list<array<string,mixed>> $rows @return list<array<string,mixed>> */

    private function enrichMany(array $rows, ?int $viewerId): array

    {

        if ($rows === []) {

            return [];

        }

        $ids = [];

        $ownerIds = [];

        foreach ($rows as $row) {

            $ids[] = (int) $row['id'];

            $ownerIds[] = (int) ($row['owner_id'] ?? 0);

        }

        $bulk = SocialService::bulkFeedStats($ids, $viewerId, $ownerIds);

        $out = [];

        foreach ($rows as $row) {

            $out[] = $this->applyEnrich($row, $viewerId, $bulk, false);

        }



        return $out;

    }



    /** @param array<string,mixed> $row */

    private function enrich(array $row, ?int $viewerId, bool $withMessages = false): array

    {

        $id = (int) $row['id'];

        $ownerId = (int) ($row['owner_id'] ?? 0);

        $bulk = SocialService::bulkFeedStats([$id], $viewerId, $ownerId > 0 ? [$ownerId] : []);



        return $this->applyEnrich($row, $viewerId, $bulk, $withMessages);

    }



    /**

     * @param array<string,mixed> $row

     * @param array{favorite_counts:array<int,int>,favorited_ids:array<int,bool>,following_ids:array<int,bool>} $bulk

     * @return array<string,mixed>

     */

    private function applyEnrich(array $row, ?int $viewerId, array $bulk, bool $withMessages): array

    {

        $id = (int) $row['id'];

        $ownerId = (int) ($row['owner_id'] ?? 0);

        $row['listing_no'] = $this->listingNoBase + $id;

        $row['photo_list'] = cx_photo_urls($row['photo_urls'] ?? '[]');

        $row['favorite_count'] = $bulk['favorite_counts'][$id] ?? 0;

        $row['is_favorited'] = isset($bulk['favorited_ids'][$id]);

        $row['is_following_owner'] = ($viewerId && $ownerId > 0)

            ? isset($bulk['following_ids'][$ownerId]) : false;

        $row['view_count'] = (int) ($row['view_count'] ?? 0);

        $row['message_count'] = $withMessages ? cx_listing_message_count($id) : 0;

        $row['days_live'] = cx_listing_days_live($row);

        $row['is_sold'] = cx_listing_is_sold((string) ($row['status'] ?? ''));

        $row['is_expired'] = ListingLifecycleService::isExpiredRow($row);



        return $row;

    }



    /** Filtre sayimlari icin hafif satir (favori sorgusu yok). */

    /** @param array<string,mixed> $row @return array<string,mixed> */

    private function lightItem(array $row): array

    {

        $row['photo_list'] = cx_photo_urls($row['photo_urls'] ?? '[]');



        return $row;

    }



    private function feedStatusSql(bool $includeSold): string

    {

        if ($includeSold) {

            return "UPPER(l.status) IN ('APPROVED','ACTIVE','SOLD')";

        }



        return "UPPER(l.status) IN ('APPROVED','ACTIVE')";

    }

    /** @return array{0:string,1:list<string>} */
    private function feedQualitySql(bool $subcategoryAlreadyFiltered): array
    {
        if (!cx_listing_quality_enabled() || !cx_listing_quality_settings()['feed_require_vehicle_attrs']) {
            return ['', []];
        }

        $extraArgs = [];
        $sql = " AND l.category = 'Araçlar'";
        if (!$subcategoryAlreadyFiltered) {
            $labels = cx_listing_quality_vehicle_subcategories();
            if ($labels !== []) {
                $sql .= ' AND l.subcategory IN (' . implode(',', array_fill(0, count($labels), '?')) . ')';
                foreach ($labels as $label) {
                    $extraArgs[] = $label;
                }
            }
        }
        $sql .= " AND l.attrs_json IS NOT NULL AND TRIM(l.attrs_json) <> '' AND l.attrs_json <> '[]'";

        return [$sql, $extraArgs];
    }

    /** @param list<array<string,mixed>> $rows @return list<array<string,mixed>> */
    private function filterFeedQualityRows(array $rows): array
    {
        if (!cx_listing_quality_enabled()) {
            return $rows;
        }

        $out = [];
        foreach ($rows as $row) {
            if (cx_listing_passes_feed_quality($row)) {
                $out[] = $row;
            }
        }

        return $out;
    }

}
