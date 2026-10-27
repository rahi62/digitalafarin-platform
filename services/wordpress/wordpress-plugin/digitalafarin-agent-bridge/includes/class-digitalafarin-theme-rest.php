<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_REST {
    private const NS = 'digitalafarin/v1';

    public static function boot(): void {
        add_action('rest_api_init', [self::class, 'register_routes']);
        add_action('init', [DigitalAfarin_Theme_Backups::class, 'maybe_upgrade']);
    }

    public static function register_routes(): void {
        register_rest_route(self::NS, '/theme/status', [[
            'methods' => WP_REST_Server::READABLE,
            'callback' => [self::class, 'status'],
            'permission_callback' => [self::class, 'can_read_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/resolve-template', [[
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [self::class, 'resolve_template'],
            'permission_callback' => [self::class, 'can_read_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/file', [[
            'methods' => WP_REST_Server::READABLE,
            'callback' => [self::class, 'read_file'],
            'permission_callback' => [self::class, 'can_read_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/file/preview', [[
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [self::class, 'preview_file'],
            'permission_callback' => [self::class, 'can_manage_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/file/update', [[
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [self::class, 'update_file'],
            'permission_callback' => [self::class, 'can_manage_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/backups', [[
            'methods' => WP_REST_Server::READABLE,
            'callback' => [self::class, 'list_backups'],
            'permission_callback' => [self::class, 'can_manage_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/backups/(?P<id>[a-f0-9-]{36})/restore', [[
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [self::class, 'restore_backup'],
            'permission_callback' => [self::class, 'can_manage_theme'],
        ]]);
        register_rest_route(self::NS, '/theme/policy', [
            [
                'methods' => WP_REST_Server::READABLE,
                'callback' => [self::class, 'get_policy'],
                'permission_callback' => [self::class, 'can_manage_theme'],
            ],
            [
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => [self::class, 'update_policy'],
                'permission_callback' => [self::class, 'can_manage_theme'],
            ],
        ]);
    }

    public static function can_read_theme(): bool {
        return current_user_can('edit_theme_options');
    }

    public static function can_manage_theme(): bool {
        return current_user_can('manage_options');
    }

    public static function status(WP_REST_Request $request) {
        $policy = DigitalAfarin_Theme_Policy::get();
        $theme = wp_get_theme();
        $validator = new DigitalAfarin_Theme_Validator($policy);
        $stylesheetDir = function_exists('get_stylesheet_directory') ? get_stylesheet_directory() : '';
        $templateDir = function_exists('get_template_directory') ? get_template_directory() : '';
        $atomic = ($stylesheetDir && is_writable($stylesheetDir)) || ($templateDir && is_writable($templateDir));
        $configured = $policy->policy();
        return rest_ensure_response([
            'theme' => [
                'name' => method_exists($theme, 'get') ? (string) $theme->get('Name') : '',
                'stylesheet' => function_exists('get_stylesheet') ? (string) get_stylesheet() : '',
                'version' => method_exists($theme, 'get') ? (string) $theme->get('Version') : '',
                'childTheme' => function_exists('is_child_theme') ? (bool) is_child_theme() : false,
            ],
            'policy' => $configured,
            'capabilities' => [
                'phpLint' => $validator->php_lint_available(),
                'atomicRename' => (bool) $atomic,
                'backup' => true,
                'httpQa' => function_exists('wp_remote_get'),
            ],
            'zipFallbackRecommended' => !$configured['enabled'] || !$configured['fullFileWriteEnabled'] || !$validator->php_lint_available() || !$atomic,
        ]);
    }

    public static function resolve_template(WP_REST_Request $request) {
        $params = $request->get_json_params();
        $input = [];
        if (isset($params['pageId'])) $input['pageId'] = (int) $params['pageId'];
        if (isset($params['url'])) $input['url'] = trim((string) $params['url']);
        $result = (new DigitalAfarin_Theme_Resolver())->resolve($input);
        return self::ensure($result);
    }

    public static function read_file(WP_REST_Request $request) {
        $relativePath = (string) $request->get_param('relativePath');
        return self::ensure((new DigitalAfarin_Theme_Resolver())->read($relativePath));
    }

    public static function preview_file(WP_REST_Request $request) {
        $params = $request->get_json_params();
        $binding = self::validate_binding($params);
        if (self::is_error($binding)) return $binding;
        $writer = new DigitalAfarin_Theme_Writer();
        $result = $writer->preview([
            'relativePath' => (string) ($params['relativePath'] ?? ''),
            'expectedHash' => (string) ($params['expectedHash'] ?? ''),
            'replacementContent' => (string) ($params['replacementContent'] ?? ''),
        ]);
        if (!self::is_error($result) && is_array($result)) {
            $result['page'] = $binding['page'];
            $result['templateImpact'] = [
                'sharedTemplate' => $binding['template']['sharedTemplate'],
                'assignedPageCount' => $binding['template']['assignedPageCount'],
                'assignedPageIds' => $binding['template']['assignedPageIds'],
            ];
        }
        return self::ensure($result);
    }

    public static function update_file(WP_REST_Request $request) {
        $params = $request->get_json_params();
        $binding = self::validate_binding($params);
        if (self::is_error($binding)) return $binding;
        $needles = self::clean_needles($params['qaNeedles'] ?? []);
        $result = (new DigitalAfarin_Theme_Writer())->write([
            'pageId' => (int) $binding['page']['id'],
            'pageUrl' => (string) $binding['page']['url'],
            'relativePath' => (string) ($params['relativePath'] ?? ''),
            'expectedHash' => (string) ($params['expectedHash'] ?? ''),
            'proposedHash' => (string) ($params['proposedHash'] ?? ''),
            'replacementContent' => (string) ($params['replacementContent'] ?? ''),
            'qaNeedles' => $needles,
        ]);
        if (!self::is_error($result) && function_exists('do_action')) do_action('digitalafarin_agent_theme_audit', 'theme.write_result', self::redact_result($result));
        return self::ensure($result);
    }

    public static function list_backups(WP_REST_Request $request) {
        $relativePath = $request->get_param('relativePath');
        $limit = (int) ($request->get_param('limit') ?: 50);
        return rest_ensure_response([
            'backups' => (new DigitalAfarin_Theme_Writer())->list_backups(
                is_string($relativePath) && $relativePath !== '' ? $relativePath : null,
                max(1, min(100, $limit))
            ),
        ]);
    }

    public static function restore_backup(WP_REST_Request $request) {
        $params = $request->get_json_params();
        $backupId = (string) $request->get_param('id');
        $expectedHash = (string) ($params['expectedCurrentHash'] ?? '');
        $result = (new DigitalAfarin_Theme_Writer())->restore($backupId, $expectedHash);
        if (!self::is_error($result) && function_exists('do_action')) do_action('digitalafarin_agent_theme_audit', 'theme.backup_restored', self::redact_result($result));
        return self::ensure($result);
    }

    public static function get_policy(WP_REST_Request $request) {
        return rest_ensure_response([
            'policy' => DigitalAfarin_Theme_Policy::get()->policy(),
            'hardDeniedFiles' => DigitalAfarin_Theme_Policy::hard_denied_files(),
            'limits' => [
                'maxFileBytes' => DigitalAfarin_Theme_Policy::MAX_FILE_BYTES_CEILING,
                'maxBackupRetentionPerFile' => DigitalAfarin_Theme_Policy::MAX_BACKUP_RETENTION,
            ],
        ]);
    }

    public static function update_policy(WP_REST_Request $request) {
        $params = $request->get_json_params();
        if (!is_array($params)) $params = [];
        $raw = [
            'enabled' => (bool) ($params['enabled'] ?? false),
            'fullFileWriteEnabled' => (bool) ($params['fullFileWriteEnabled'] ?? false),
            'allowedFiles' => self::clean_list($params['allowedFiles'] ?? []),
            'allowedDirectories' => self::clean_list($params['allowedDirectories'] ?? []),
            'maxFileBytes' => isset($params['maxFileBytes']) ? (int) $params['maxFileBytes'] : 1048576,
            'backupRetentionPerFile' => isset($params['backupRetentionPerFile']) ? (int) $params['backupRetentionPerFile'] : 20,
            'autoRollbackOnQaFailure' => (bool) ($params['autoRollbackOnQaFailure'] ?? true),
        ];
        $validation = DigitalAfarin_Theme_Policy::validate_update($raw);
        if (!$validation['valid']) {
            return new WP_Error('digitalafarin_invalid_theme_policy', 'Theme automation policy contains unsafe or invalid entries.', [
                'status' => 400,
                'errors' => $validation['errors'],
            ]);
        }
        update_option(DigitalAfarin_Theme_Policy::OPTION, $validation['policy'], false);
        if (function_exists('do_action')) do_action('digitalafarin_agent_theme_audit', 'theme.policy_updated', [
            'enabled' => $validation['policy']['enabled'],
            'fullFileWriteEnabled' => $validation['policy']['fullFileWriteEnabled'],
            'allowedFileCount' => count($validation['policy']['allowedFiles']),
            'allowedDirectoryCount' => count($validation['policy']['allowedDirectories']),
        ]);
        return rest_ensure_response([
            'updated' => true,
            'policy' => $validation['policy'],
            'hardDeniedFiles' => DigitalAfarin_Theme_Policy::hard_denied_files(),
        ]);
    }

    private static function validate_binding(array $params) {
        $pageId = (int) ($params['pageId'] ?? 0);
        $relativePath = (string) ($params['relativePath'] ?? '');
        if ($pageId <= 0 || $relativePath === '') {
            return new WP_Error('digitalafarin_theme_binding_required', 'pageId and relativePath are required.', ['status' => 400]);
        }
        $resolved = (new DigitalAfarin_Theme_Resolver())->resolve(['pageId' => $pageId]);
        if (self::is_error($resolved)) return $resolved;
        if (($resolved['template']['relativePath'] ?? '') !== $relativePath) {
            return new WP_Error('digitalafarin_theme_binding_mismatch', 'Requested file is not the template currently resolved for this Page.', [
                'status' => 409,
                'resolvedRelativePath' => $resolved['template']['relativePath'] ?? null,
            ]);
        }
        return $resolved;
    }

    private static function clean_list($value): array {
        if (!is_array($value)) return [];
        $result = [];
        foreach (array_slice($value, 0, 200) as $item) {
            $item = function_exists('wp_unslash') ? wp_unslash((string) $item) : (string) $item;
            $item = trim($item);
            if ($item !== '') $result[] = $item;
        }
        return array_values(array_unique($result));
    }

    private static function clean_needles($value): array {
        if (!is_array($value)) return [];
        $result = [];
        foreach (array_slice($value, 0, 20) as $item) {
            $item = function_exists('sanitize_text_field') ? sanitize_text_field((string) $item) : trim((string) $item);
            if ($item !== '') $result[] = substr($item, 0, 500);
        }
        return $result;
    }

    private static function redact_result(array $result): array {
        unset($result['replacementContent'], $result['originalContent'], $result['content']);
        return $result;
    }

    private static function is_error($value): bool {
        return class_exists('WP_Error') && $value instanceof WP_Error;
    }

    private static function ensure($value) {
        return self::is_error($value) ? $value : rest_ensure_response($value);
    }
}
