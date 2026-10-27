<?php

declare(strict_types=1);

interface DigitalAfarin_Theme_Backup_Store {
    public function create(array $record): string;
    public function get(string $id): ?array;
    public function list(string $themeStylesheet, ?string $relativePath = null, int $limit = 50): array;
    public function mark_restored(string $id, string $restoreOperationId): void;
    public function trim(string $themeStylesheet, string $relativePath, int $keep): void;
}

final class DigitalAfarin_Theme_Backups implements DigitalAfarin_Theme_Backup_Store {
    public const SCHEMA_VERSION = '1';
    private const SCHEMA_OPTION = 'digitalafarin_theme_backup_schema_version';

    public static function maybe_upgrade(): void {
        if (!function_exists('get_option') || !function_exists('update_option')) return;
        if ((string) get_option(self::SCHEMA_OPTION, '') === self::SCHEMA_VERSION) return;
        global $wpdb;
        if (!$wpdb) return;
        $table = self::table_name($wpdb);
        $charset = method_exists($wpdb, 'get_charset_collate') ? $wpdb->get_charset_collate() : '';
        $sql = "CREATE TABLE {$table} (
            id varchar(36) NOT NULL,
            theme_stylesheet varchar(191) NOT NULL,
            relative_path text NOT NULL,
            page_id bigint(20) unsigned NULL,
            operation_id varchar(36) NOT NULL,
            original_hash char(64) NOT NULL,
            replacement_hash char(64) NOT NULL,
            original_content longtext NOT NULL,
            created_by bigint(20) unsigned NOT NULL DEFAULT 0,
            created_at datetime NOT NULL,
            restored_at datetime NULL,
            restore_operation_id varchar(36) NULL,
            PRIMARY KEY  (id),
            KEY theme_path (theme_stylesheet(100), relative_path(150)),
            KEY created_at (created_at)
        ) {$charset};";
        if (!function_exists('dbDelta')) {
            $upgrade = ABSPATH . 'wp-admin/includes/upgrade.php';
            if (is_file($upgrade)) require_once $upgrade;
        }
        if (function_exists('dbDelta')) dbDelta($sql);
        update_option(self::SCHEMA_OPTION, self::SCHEMA_VERSION, false);
    }

    public function create(array $record): string {
        global $wpdb;
        $id = $this->uuid();
        $table = self::table_name($wpdb);
        $inserted = $wpdb->insert($table, [
            'id' => $id,
            'theme_stylesheet' => (string) ($record['theme_stylesheet'] ?? ''),
            'relative_path' => (string) ($record['relative_path'] ?? ''),
            'page_id' => isset($record['page_id']) ? (int) $record['page_id'] : null,
            'operation_id' => (string) ($record['operation_id'] ?? ''),
            'original_hash' => (string) ($record['original_hash'] ?? ''),
            'replacement_hash' => (string) ($record['replacement_hash'] ?? ''),
            'original_content' => (string) ($record['original_content'] ?? ''),
            'created_by' => function_exists('get_current_user_id') ? (int) get_current_user_id() : 0,
            'created_at' => function_exists('current_time') ? current_time('mysql', true) : gmdate('Y-m-d H:i:s'),
        ], ['%s','%s','%s','%d','%s','%s','%s','%s','%d','%s']);
        if ($inserted === false) throw new RuntimeException('Theme backup insert failed.');
        return $id;
    }

    public function get(string $id): ?array {
        global $wpdb;
        $table = self::table_name($wpdb);
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE id = %s LIMIT 1", $id), ARRAY_A);
        return is_array($row) ? $row : null;
    }

    public function list(string $themeStylesheet, ?string $relativePath = null, int $limit = 50): array {
        global $wpdb;
        $table = self::table_name($wpdb);
        $limit = max(1, min(100, $limit));
        if ($relativePath !== null && $relativePath !== '') {
            $sql = $wpdb->prepare(
                "SELECT id,theme_stylesheet,relative_path,page_id,operation_id,original_hash,replacement_hash,created_by,created_at,restored_at,restore_operation_id FROM {$table} WHERE theme_stylesheet=%s AND relative_path=%s ORDER BY created_at DESC LIMIT %d",
                $themeStylesheet, $relativePath, $limit
            );
        } else {
            $sql = $wpdb->prepare(
                "SELECT id,theme_stylesheet,relative_path,page_id,operation_id,original_hash,replacement_hash,created_by,created_at,restored_at,restore_operation_id FROM {$table} WHERE theme_stylesheet=%s ORDER BY created_at DESC LIMIT %d",
                $themeStylesheet, $limit
            );
        }
        $rows = $wpdb->get_results($sql, ARRAY_A);
        return is_array($rows) ? $rows : [];
    }

    public function mark_restored(string $id, string $restoreOperationId): void {
        global $wpdb;
        $wpdb->update(self::table_name($wpdb), [
            'restored_at' => function_exists('current_time') ? current_time('mysql', true) : gmdate('Y-m-d H:i:s'),
            'restore_operation_id' => $restoreOperationId,
        ], ['id' => $id], ['%s','%s'], ['%s']);
    }

    public function trim(string $themeStylesheet, string $relativePath, int $keep): void {
        global $wpdb;
        $keep = max(1, min(DigitalAfarin_Theme_Policy::MAX_BACKUP_RETENTION, $keep));
        $table = self::table_name($wpdb);
        $ids = $wpdb->get_col($wpdb->prepare(
            "SELECT id FROM {$table} WHERE theme_stylesheet=%s AND relative_path=%s ORDER BY created_at DESC LIMIT 1000 OFFSET %d",
            $themeStylesheet, $relativePath, $keep
        ));
        if (!$ids) return;
        $placeholders = implode(',', array_fill(0, count($ids), '%s'));
        $wpdb->query($wpdb->prepare("DELETE FROM {$table} WHERE id IN ({$placeholders})", ...array_map('strval', $ids)));
    }

    private static function table_name($wpdb): string {
        return $wpdb->prefix . 'digitalafarin_theme_backups';
    }

    private function uuid(): string {
        if (function_exists('wp_generate_uuid4')) return wp_generate_uuid4();
        $data = random_bytes(16);
        $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
        $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
    }
}
