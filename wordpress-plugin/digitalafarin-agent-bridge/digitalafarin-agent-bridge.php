<?php
/**
 * Plugin Name: DigitalAfarin Agent Bridge
 * Description: Authenticated bridge for controlled SEO, indexing, redirects, and safe theme template automation by the DigitalAfarin WordPress Agent.
 * Version: 0.4.0
 * Author: DigitalAfarin
 * Requires at least: 6.5
 * Requires PHP: 8.1
 */

defined('ABSPATH') || exit;

foreach ([
    'class-digitalafarin-theme-policy.php',
    'class-digitalafarin-theme-resolver.php',
    'class-digitalafarin-theme-validator.php',
    'class-digitalafarin-theme-backups.php',
    'class-digitalafarin-theme-writer.php',
    'class-digitalafarin-theme-audit.php',
    'class-digitalafarin-theme-rest.php',
] as $digitalafarin_theme_file) {
    require_once __DIR__ . '/includes/' . $digitalafarin_theme_file;
}
unset($digitalafarin_theme_file);

final class DigitalAfarin_Agent_Bridge {
    private const NS = 'digitalafarin/v1';
    private const WRITABLE_STATUSES = ['draft', 'publish'];
    private const NOINDEX_META = '_digitalafarin_agent_noindex';
    private const REDIRECT_OPTION = 'digitalafarin_agent_redirects';

    public static function boot(): void {
        add_action('rest_api_init', [self::class, 'register_routes']);
        add_action('template_redirect', [self::class, 'handle_redirect'], 0);

        add_filter('wp_robots', [self::class, 'filter_core_robots']);
        add_filter('wpseo_robots_array', [self::class, 'filter_seo_robots']);
        add_filter('rank_math/frontend/robots', [self::class, 'filter_seo_robots']);

        // A custom noindex override should not leave the same URL advertised in XML sitemaps.
        add_filter('wpseo_exclude_from_sitemap_by_post_ids', [self::class, 'filter_yoast_sitemap_excludes']);
        add_filter('rank_math/sitemap/entry', [self::class, 'filter_rank_math_sitemap_entry'], 10, 3);
    }

    public static function register_routes(): void {
        register_rest_route(self::NS, '/posts/(?P<id>\d+)/seo', [
            [
                'methods' => WP_REST_Server::READABLE,
                'callback' => [self::class, 'get_seo'],
                'permission_callback' => [self::class, 'can_edit_post'],
                'args' => self::post_id_args(),
            ],
            [
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => [self::class, 'update_seo'],
                'permission_callback' => [self::class, 'can_edit_post'],
                'args' => self::post_id_args(),
            ],
        ]);

        register_rest_route(self::NS, '/posts/(?P<id>\d+)/indexing', [
            [
                'methods' => WP_REST_Server::READABLE,
                'callback' => [self::class, 'get_indexing'],
                'permission_callback' => [self::class, 'can_edit_post'],
                'args' => self::post_id_args(),
            ],
            [
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => [self::class, 'update_indexing'],
                'permission_callback' => [self::class, 'can_edit_post'],
                'args' => self::post_id_args(),
            ],
        ]);

        register_rest_route(self::NS, '/redirects', [
            [
                'methods' => WP_REST_Server::READABLE,
                'callback' => [self::class, 'list_redirects'],
                'permission_callback' => [self::class, 'can_manage_redirects'],
            ],
            [
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => [self::class, 'create_redirect'],
                'permission_callback' => [self::class, 'can_manage_redirects'],
            ],
        ]);

        register_rest_route(self::NS, '/redirects/(?P<id>[a-f0-9-]{36})', [
            [
                'methods' => WP_REST_Server::DELETABLE,
                'callback' => [self::class, 'delete_redirect'],
                'permission_callback' => [self::class, 'can_manage_redirects'],
            ],
        ]);
    }

    private static function post_id_args(): array {
        return [
            'id' => [
                'validate_callback' => static fn($value): bool => is_numeric($value) && (int) $value > 0,
            ],
        ];
    }

    public static function can_edit_post(WP_REST_Request $request): bool {
        $post_id = (int) $request['id'];
        return $post_id > 0 && current_user_can('edit_post', $post_id);
    }

    public static function can_manage_redirects(): bool {
        return current_user_can('manage_options');
    }

    private static function provider(): ?string {
        if (defined('RANK_MATH_VERSION') || class_exists('RankMath')) {
            return 'rank-math';
        }
        if (defined('WPSEO_VERSION') || class_exists('WPSEO_Options')) {
            return 'yoast';
        }
        return null;
    }

    private static function keys(string $provider): array {
        if ($provider === 'rank-math') {
            return [
                'title' => 'rank_math_title',
                'description' => 'rank_math_description',
                'focusKeyword' => 'rank_math_focus_keyword',
                'canonical' => 'rank_math_canonical_url',
            ];
        }
        return [
            'title' => '_yoast_wpseo_title',
            'description' => '_yoast_wpseo_metadesc',
            'focusKeyword' => '_yoast_wpseo_focuskw',
            'canonical' => '_yoast_wpseo_canonical',
        ];
    }

    private static function truncate(string $value, int $length): string {
        if (function_exists('mb_substr')) {
            return mb_substr($value, 0, $length);
        }
        return substr($value, 0, $length);
    }

    private static function is_writable_status(string $status): bool {
        return in_array($status, self::WRITABLE_STATUSES, true);
    }

    private static function response_fields(int $post_id, string $provider): array {
        $keys = self::keys($provider);
        return [
            'title' => (string) get_post_meta($post_id, $keys['title'], true),
            'description' => (string) get_post_meta($post_id, $keys['description'], true),
            'focusKeyword' => (string) get_post_meta($post_id, $keys['focusKeyword'], true),
            'canonical' => (string) get_post_meta($post_id, $keys['canonical'], true),
        ];
    }

    public static function get_seo(WP_REST_Request $request) {
        $post_id = (int) $request['id'];
        $post = get_post($post_id);
        if (!$post) {
            return new WP_Error('digitalafarin_post_not_found', 'Post not found.', ['status' => 404]);
        }

        $provider = self::provider();
        if (!$provider) {
            return new WP_Error('digitalafarin_seo_provider_missing', 'Rank Math or Yoast SEO is not active.', ['status' => 409]);
        }

        return rest_ensure_response([
            'provider' => $provider,
            'writable' => self::is_writable_status($post->post_status),
            'status' => $post->post_status,
            'fields' => self::response_fields($post_id, $provider),
        ]);
    }

    public static function update_seo(WP_REST_Request $request) {
        $post_id = (int) $request['id'];
        $post = get_post($post_id);
        if (!$post) {
            return new WP_Error('digitalafarin_post_not_found', 'Post not found.', ['status' => 404]);
        }
        if (!self::is_writable_status($post->post_status)) {
            return new WP_Error(
                'digitalafarin_status_not_writable',
                'SEO metadata may only be changed for draft or published posts.',
                ['status' => 409]
            );
        }

        $provider = self::provider();
        if (!$provider) {
            return new WP_Error('digitalafarin_seo_provider_missing', 'Rank Math or Yoast SEO is not active.', ['status' => 409]);
        }

        $params = $request->get_json_params();
        if (!is_array($params)) {
            $params = [];
        }

        $keys = self::keys($provider);
        $sanitizers = [
            'title' => static fn($value): string => self::truncate(sanitize_text_field((string) $value), 300),
            'description' => static fn($value): string => self::truncate(sanitize_textarea_field((string) $value), 1000),
            'focusKeyword' => static fn($value): string => self::truncate(sanitize_text_field((string) $value), 500),
            'canonical' => static fn($value): string => self::truncate(esc_url_raw((string) $value), 2048),
        ];

        $changed = [];
        foreach ($keys as $field => $meta_key) {
            if (!array_key_exists($field, $params)) {
                continue;
            }
            $value = $sanitizers[$field]($params[$field]);
            if ($value === '') {
                delete_post_meta($post_id, $meta_key);
            } else {
                update_post_meta($post_id, $meta_key, $value);
            }
            $changed[] = $field;
        }

        if (!$changed) {
            return new WP_Error('digitalafarin_no_fields', 'At least one SEO field must be provided.', ['status' => 400]);
        }

        return rest_ensure_response([
            'provider' => $provider,
            'writable' => true,
            'status' => $post->post_status,
            'changed' => $changed,
            'fields' => self::response_fields($post_id, $provider),
        ]);
    }

    public static function get_indexing(WP_REST_Request $request) {
        $post_id = (int) $request['id'];
        $post = get_post($post_id);
        if (!$post) {
            return new WP_Error('digitalafarin_post_not_found', 'Post not found.', ['status' => 404]);
        }
        return rest_ensure_response([
            'postId' => $post_id,
            'status' => $post->post_status,
            'noindex' => get_post_meta($post_id, self::NOINDEX_META, true) === '1',
            'source' => 'digitalafarin-bridge',
        ]);
    }

    public static function update_indexing(WP_REST_Request $request) {
        $post_id = (int) $request['id'];
        $post = get_post($post_id);
        if (!$post) {
            return new WP_Error('digitalafarin_post_not_found', 'Post not found.', ['status' => 404]);
        }
        if (!self::is_writable_status($post->post_status)) {
            return new WP_Error(
                'digitalafarin_status_not_writable',
                'Noindex may only be changed for draft or published posts.',
                ['status' => 409]
            );
        }

        $params = $request->get_json_params();
        if (!is_array($params) || !array_key_exists('noindex', $params) || !is_bool($params['noindex'])) {
            return new WP_Error('digitalafarin_invalid_noindex', 'noindex must be a boolean.', ['status' => 400]);
        }

        if ($params['noindex']) {
            update_post_meta($post_id, self::NOINDEX_META, '1');
        } else {
            delete_post_meta($post_id, self::NOINDEX_META);
        }

        return self::get_indexing($request);
    }

    private static function queried_post_is_noindex(): bool {
        if (!is_singular()) {
            return false;
        }
        $post_id = get_queried_object_id();
        return $post_id > 0 && get_post_meta($post_id, self::NOINDEX_META, true) === '1';
    }

    private static function post_is_noindex(int $post_id): bool {
        return $post_id > 0 && get_post_meta($post_id, self::NOINDEX_META, true) === '1';
    }

    public static function filter_core_robots(array $robots): array {
        if (self::queried_post_is_noindex()) {
            unset($robots['index']);
            $robots['noindex'] = true;
        }
        return $robots;
    }

    public static function filter_seo_robots($robots) {
        if (!self::queried_post_is_noindex() || !is_array($robots)) {
            return $robots;
        }
        unset($robots['index']);
        $robots['noindex'] = 'noindex';
        return $robots;
    }

    public static function filter_yoast_sitemap_excludes($post_ids): array {
        $ids = is_array($post_ids) ? array_map('intval', $post_ids) : [];
        global $wpdb;
        $forced = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT DISTINCT post_id FROM {$wpdb->postmeta} WHERE meta_key = %s AND meta_value = %s",
                self::NOINDEX_META,
                '1'
            )
        );
        foreach ($forced as $post_id) {
            $ids[] = (int) $post_id;
        }
        return array_values(array_unique(array_filter($ids)));
    }

    public static function filter_rank_math_sitemap_entry($url, $type, $object) {
        if ($type === 'post' && is_object($object) && isset($object->ID) && self::post_is_noindex((int) $object->ID)) {
            return false;
        }
        return $url;
    }

    private static function normalize_source_path(string $value): ?string {
        $value = trim($value);
        if ($value === '' || str_contains($value, '://') || str_starts_with($value, '//')) {
            return null;
        }
        $path = wp_parse_url($value, PHP_URL_PATH);
        if (!is_string($path)) {
            return null;
        }
        $path = '/' . ltrim($path, '/');
        if ($path !== '/') {
            $path = untrailingslashit($path);
        }
        return $path;
    }

    private static function normalize_target(string $value): ?string {
        $value = trim($value);
        if ($value === '') {
            return null;
        }
        if (str_starts_with($value, '/') && !str_starts_with($value, '//')) {
            return '/' . ltrim($value, '/');
        }
        $url = wp_parse_url($value);
        if (!is_array($url) || empty($url['scheme']) || empty($url['host'])) {
            return null;
        }
        if (!in_array(strtolower((string) $url['scheme']), ['http', 'https'], true)) {
            return null;
        }
        return esc_url_raw($value);
    }

    private static function same_site_target_path(string $target): ?string {
        if (str_starts_with($target, '/') && !str_starts_with($target, '//')) {
            return self::normalize_source_path($target);
        }
        $target_url = wp_parse_url($target);
        $home_url = wp_parse_url(home_url('/'));
        if (!is_array($target_url) || !is_array($home_url) || empty($target_url['host']) || empty($home_url['host'])) {
            return null;
        }
        $target_port = isset($target_url['port']) ? (int) $target_url['port'] : null;
        $home_port = isset($home_url['port']) ? (int) $home_url['port'] : null;
        if (strtolower((string) $target_url['host']) !== strtolower((string) $home_url['host']) || $target_port !== $home_port) {
            return null;
        }
        return self::normalize_source_path((string) ($target_url['path'] ?? '/'));
    }

    private static function redirects(): array {
        $redirects = get_option(self::REDIRECT_OPTION, []);
        return is_array($redirects) ? array_values(array_filter($redirects, 'is_array')) : [];
    }

    private static function save_redirects(array $redirects): void {
        update_option(self::REDIRECT_OPTION, array_values($redirects), false);
    }

    private static function would_create_redirect_cycle(string $source, string $target, array $redirects): bool {
        $current = self::same_site_target_path($target);
        if ($current === null) {
            return false;
        }
        $visited = [];
        for ($step = 0; $step < 100 && $current !== null; $step++) {
            if ($current === $source || isset($visited[$current])) {
                return true;
            }
            $visited[$current] = true;
            $next = null;
            foreach ($redirects as $redirect) {
                if (!empty($redirect['enabled']) && ($redirect['source'] ?? null) === $current) {
                    $next = self::same_site_target_path((string) ($redirect['target'] ?? ''));
                    break;
                }
            }
            $current = $next;
        }
        return $current !== null;
    }

    public static function list_redirects() {
        $redirects = self::redirects();
        usort($redirects, static fn(array $a, array $b): int => strcmp((string) ($b['createdAt'] ?? ''), (string) ($a['createdAt'] ?? '')));
        return rest_ensure_response(['redirects' => $redirects]);
    }

    public static function create_redirect(WP_REST_Request $request) {
        $params = $request->get_json_params();
        $source = self::normalize_source_path((string) ($params['source'] ?? ''));
        $target = self::normalize_target((string) ($params['target'] ?? ''));
        if (!$source || !$target) {
            return new WP_Error('digitalafarin_invalid_redirect', 'A relative source path and valid HTTP(S) or relative target are required.', ['status' => 400]);
        }

        $redirects = self::redirects();
        foreach ($redirects as $redirect) {
            if (($redirect['source'] ?? null) === $source) {
                return new WP_Error('digitalafarin_redirect_exists', 'A redirect for this source path already exists.', ['status' => 409]);
            }
        }
        if (self::would_create_redirect_cycle($source, $target, $redirects)) {
            return new WP_Error('digitalafarin_redirect_loop', 'This redirect would create a direct or chained redirect loop.', ['status' => 409]);
        }

        $now = gmdate('c');
        $redirect = [
            'id' => wp_generate_uuid4(),
            'source' => $source,
            'target' => $target,
            'statusCode' => 301,
            'enabled' => true,
            'createdAt' => $now,
            'updatedAt' => $now,
        ];
        $redirects[] = $redirect;
        self::save_redirects($redirects);
        return new WP_REST_Response(['redirect' => $redirect], 201);
    }

    public static function delete_redirect(WP_REST_Request $request) {
        $id = sanitize_text_field((string) $request['id']);
        $redirects = self::redirects();
        $found = null;
        $kept = [];
        foreach ($redirects as $redirect) {
            if (($redirect['id'] ?? '') === $id) {
                $found = $redirect;
                continue;
            }
            $kept[] = $redirect;
        }
        if (!$found) {
            return new WP_Error('digitalafarin_redirect_not_found', 'Redirect not found.', ['status' => 404]);
        }
        self::save_redirects($kept);
        return rest_ensure_response(['deleted' => true, 'redirect' => $found]);
    }

    public static function handle_redirect(): void {
        if (is_admin() || wp_doing_ajax() || wp_doing_cron() || (defined('REST_REQUEST') && REST_REQUEST)) {
            return;
        }
        $request_uri = isset($_SERVER['REQUEST_URI']) ? (string) wp_unslash($_SERVER['REQUEST_URI']) : '/';
        $path = wp_parse_url($request_uri, PHP_URL_PATH);
        $source = self::normalize_source_path(is_string($path) ? $path : '/');
        if (!$source) {
            return;
        }
        foreach (self::redirects() as $redirect) {
            if (!empty($redirect['enabled']) && ($redirect['source'] ?? null) === $source) {
                $target = (string) ($redirect['target'] ?? '');
                if ($target !== '') {
                    wp_redirect($target, 301, 'DigitalAfarin Agent Bridge');
                    exit;
                }
            }
        }
    }
}

DigitalAfarin_Agent_Bridge::boot();
DigitalAfarin_Theme_Audit::boot();
DigitalAfarin_Theme_REST::boot();
