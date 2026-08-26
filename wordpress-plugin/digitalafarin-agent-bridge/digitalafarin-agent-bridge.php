<?php
/**
 * Plugin Name: DigitalAfarin Agent Bridge
 * Description: Adds a narrow authenticated REST bridge for draft-only SEO metadata management by the DigitalAfarin WordPress Agent.
 * Version: 0.1.0
 * Author: DigitalAfarin
 * Requires at least: 6.5
 * Requires PHP: 8.1
 */

defined('ABSPATH') || exit;

final class DigitalAfarin_Agent_Bridge {
    private const NS = 'digitalafarin/v1';

    public static function boot(): void {
        add_action('rest_api_init', [self::class, 'register_routes']);
    }

    public static function register_routes(): void {
        register_rest_route(self::NS, '/posts/(?P<id>\d+)/seo', [
            [
                'methods' => WP_REST_Server::READABLE,
                'callback' => [self::class, 'get_seo'],
                'permission_callback' => [self::class, 'can_edit_post'],
                'args' => [
                    'id' => [
                        'validate_callback' => static fn($value): bool => is_numeric($value) && (int) $value > 0,
                    ],
                ],
            ],
            [
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => [self::class, 'update_seo'],
                'permission_callback' => [self::class, 'can_edit_post'],
                'args' => [
                    'id' => [
                        'validate_callback' => static fn($value): bool => is_numeric($value) && (int) $value > 0,
                    ],
                ],
            ],
        ]);
    }

    public static function can_edit_post(WP_REST_Request $request): bool {
        $post_id = (int) $request['id'];
        return $post_id > 0 && current_user_can('edit_post', $post_id);
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
            'writable' => $post->post_status === 'draft',
            'fields' => self::response_fields($post_id, $provider),
        ]);
    }

    public static function update_seo(WP_REST_Request $request) {
        $post_id = (int) $request['id'];
        $post = get_post($post_id);
        if (!$post) {
            return new WP_Error('digitalafarin_post_not_found', 'Post not found.', ['status' => 404]);
        }
        if ($post->post_status !== 'draft') {
            return new WP_Error('digitalafarin_not_draft', 'SEO metadata may only be changed for draft posts.', ['status' => 409]);
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
            'changed' => $changed,
            'fields' => self::response_fields($post_id, $provider),
        ]);
    }
}

DigitalAfarin_Agent_Bridge::boot();
