<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_Audit {
    public const OPTION = 'digitalafarin_agent_theme_audit_log';
    private const MAX_EVENTS = 200;
    private const BLOCKED_KEYS = [
        'content', 'replacementcontent', 'originalcontent', 'backupcontent',
        'apppassword', 'password', 'secret', 'token', 'authorization',
    ];

    public static function boot(): void {
        add_action('digitalafarin_agent_theme_audit', [self::class, 'record'], 10, 2);
        add_action('rest_api_init', [self::class, 'register_route']);
        add_filter('rest_pre_dispatch', [self::class, 'before_dispatch'], 10, 3);
        add_filter('rest_request_after_callbacks', [self::class, 'after_callbacks'], 10, 3);
    }

    public static function register_route(): void {
        register_rest_route('digitalafarin/v1', '/theme/audit', [[
            'methods' => WP_REST_Server::READABLE,
            'callback' => static function (WP_REST_Request $request) {
                $limit = (int) ($request->get_param('limit') ?: 50);
                return rest_ensure_response(['events' => self::recent($limit)]);
            },
            'permission_callback' => static fn(): bool => current_user_can('manage_options'),
        ]]);
    }

    public static function before_dispatch($result, $server, $request) {
        if (!($request instanceof WP_REST_Request)) return $result;
        $route = $request->get_route();
        if ($route === '/digitalafarin/v1/theme/file/update' && strtoupper($request->get_method()) === 'POST') {
            self::record('theme.write_started', self::request_details($request));
        }
        return $result;
    }

    public static function after_callbacks($response, $handler, $request) {
        if (!($request instanceof WP_REST_Request)) return $response;
        $route = $request->get_route();
        $method = strtoupper($request->get_method());
        $event = null;

        if ($route === '/digitalafarin/v1/theme/resolve-template' && $method === 'POST') $event = 'theme.template_resolved';
        elseif ($route === '/digitalafarin/v1/theme/file' && $method === 'GET') $event = 'theme.template_read';
        elseif ($route === '/digitalafarin/v1/theme/file/preview' && $method === 'POST') $event = 'theme.preview_created';
        elseif ($route === '/digitalafarin/v1/theme/file/update' && $method === 'POST') $event = 'theme.write_succeeded';
        elseif (preg_match('#^/digitalafarin/v1/theme/backups/[a-f0-9-]{36}/restore$#i', $route) && $method === 'POST') $event = 'theme.backup_restored';

        if ($event === null) return $response;

        $isError = function_exists('is_wp_error') && is_wp_error($response);
        $data = self::response_data($response);
        $details = array_merge(self::request_details($request), is_array($data) ? $data : []);

        if ($isError) {
            $details['code'] = method_exists($response, 'get_error_code') ? (string) $response->get_error_code() : 'unknown';
            self::record('theme.write_blocked', $details);
            return $response;
        }

        if ($route === '/digitalafarin/v1/theme/file/preview' && is_array($data) && array_key_exists('eligible', $data) && !$data['eligible']) {
            self::record('theme.write_blocked', $details);
            return $response;
        }

        if ($route === '/digitalafarin/v1/theme/file/update' && is_array($data)) {
            $qa = is_array($data['qa'] ?? null) ? $data['qa'] : [];
            if (array_key_exists('passed', $qa) && !$qa['passed']) {
                self::record('theme.qa_failed', $details);
                if (!empty($data['rolledBack'])) self::record('theme.auto_rollback_succeeded', $details);
                elseif (!empty($data['rollbackError'])) self::record('theme.auto_rollback_failed', $details);
            }
            if (!empty($data['written'])) self::record('theme.write_succeeded', $details);
            return $response;
        }

        self::record($event, $details);
        return $response;
    }

    public static function record(string $action, $details = []): void {
        if (!function_exists('get_option') || !function_exists('update_option')) return;
        $events = get_option(self::OPTION, []);
        if (!is_array($events)) $events = [];

        array_unshift($events, [
            'id' => function_exists('wp_generate_uuid4') ? wp_generate_uuid4() : self::uuid(),
            'action' => substr(trim($action), 0, 100),
            'details' => self::redact(is_array($details) ? $details : []),
            'userId' => function_exists('get_current_user_id') ? (int) get_current_user_id() : 0,
            'createdAt' => gmdate('c'),
        ]);

        update_option(self::OPTION, array_slice($events, 0, self::MAX_EVENTS), false);
    }

    public static function recent(int $limit = 50): array {
        if (!function_exists('get_option')) return [];
        $events = get_option(self::OPTION, []);
        if (!is_array($events)) return [];
        return array_values(array_slice($events, 0, max(1, min(100, $limit))));
    }

    public static function redact(array $details): array {
        $result = [];
        foreach ($details as $key => $value) {
            $keyString = (string) $key;
            if (in_array(strtolower($keyString), self::BLOCKED_KEYS, true)) continue;
            if (is_array($value)) {
                $result[$keyString] = self::redact($value);
            } elseif (is_bool($value) || is_int($value) || is_float($value) || $value === null) {
                $result[$keyString] = $value;
            } elseif (is_string($value)) {
                $result[$keyString] = substr($value, 0, 1000);
            }
        }
        return $result;
    }

    private static function request_details(WP_REST_Request $request): array {
        $params = $request->get_params();
        return self::redact(is_array($params) ? $params : []);
    }

    private static function response_data($response) {
        if (function_exists('is_wp_error') && is_wp_error($response)) {
            $data = method_exists($response, 'get_error_data') ? $response->get_error_data() : [];
            return is_array($data) ? $data : [];
        }
        if (is_object($response) && method_exists($response, 'get_data')) return $response->get_data();
        return is_array($response) ? $response : [];
    }

    private static function uuid(): string {
        $data = random_bytes(16);
        $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
        $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
    }
}
