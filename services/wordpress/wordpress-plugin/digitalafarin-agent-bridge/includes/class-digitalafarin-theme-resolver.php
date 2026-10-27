<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_Resolver {
    private DigitalAfarin_Theme_Policy $policy;

    public function __construct(?DigitalAfarin_Theme_Policy $policy = null) {
        $this->policy = $policy ?? DigitalAfarin_Theme_Policy::get();
    }

    public function resolve(array $input) {
        $pageId = isset($input['pageId']) ? (int) $input['pageId'] : 0;
        if ($pageId <= 0 && isset($input['url'])) {
            $pageId = $this->resolve_url_to_id((string) $input['url']);
        }
        if ($pageId <= 0) {
            return $this->error('digitalafarin_page_not_found', 'Page could not be resolved.', 404);
        }

        $post = get_post($pageId);
        if (!$post) {
            return $this->error('digitalafarin_page_not_found', 'Page not found.', 404);
        }
        if (($post->post_type ?? '') !== 'page') {
            return $this->error('digitalafarin_not_a_page', 'Resolved content is not a WordPress Page.', 409, [
                'contentType' => (string) ($post->post_type ?? 'unknown'),
                'postId' => $pageId,
            ]);
        }

        $assignedSlug = (string) get_page_template_slug($pageId);
        $actualPath = $this->resolve_template_path($post, $assignedSlug);
        if (!$actualPath) {
            return $this->error('digitalafarin_template_not_found', 'WordPress could not resolve a theme template for this Page.', 404);
        }

        $template = $this->describe_actual_template($actualPath);
        if (!$template) {
            return $this->error('digitalafarin_template_outside_active_theme', 'Resolved template is outside active theme roots.', 409);
        }

        $relativePath = $template['relativePath'];
        $assignments = $this->template_assignments($assignedSlug, $relativePath, $pageId);
        $readDecision = $this->policy->can_read($relativePath);
        $writeDecision = $this->policy->can_write($relativePath);
        $theme = wp_get_theme();
        $validator = class_exists('DigitalAfarin_Theme_Validator') ? new DigitalAfarin_Theme_Validator($this->policy) : null;
        $fileSize = filesize($actualPath) ?: 0;
        $maxFileBytes = (int) ($this->policy->policy()['maxFileBytes'] ?? 1048576);

        return [
            'page' => [
                'id' => $pageId,
                'url' => function_exists('get_permalink') ? (string) get_permalink($pageId) : '',
                'slug' => (string) ($post->post_name ?? ''),
                'status' => (string) ($post->post_status ?? ''),
            ],
            'theme' => [
                'name' => method_exists($theme, 'get') ? (string) $theme->get('Name') : '',
                'stylesheet' => function_exists('get_stylesheet') ? (string) get_stylesheet() : '',
                'version' => method_exists($theme, 'get') ? (string) $theme->get('Version') : '',
                'childTheme' => function_exists('is_child_theme') ? (bool) is_child_theme() : false,
            ],
            'template' => [
                'assignedSlug' => $assignedSlug ?: 'default',
                'relativePath' => $relativePath,
                'themeRoot' => $template['themeRoot'],
                'sizeBytes' => $fileSize,
                'modifiedAt' => filemtime($actualPath) ?: 0,
                'sha256' => hash_file('sha256', $actualPath) ?: '',
                'sharedTemplate' => $assignments['sharedTemplate'],
                'assignedPageCount' => count($assignments['pageIds']),
                'assignedPageIds' => $assignments['pageIds'],
                'readAllowed' => (bool) ($readDecision['allowed'] ?? false) && $fileSize <= $maxFileBytes,
                'writeAllowed' => (bool) ($writeDecision['allowed'] ?? false),
                'writeBlockReasons' => ($writeDecision['allowed'] ?? false) ? [] : [(string) ($writeDecision['reason'] ?? 'theme_write_blocked')],
                'readBlockReasons' => $fileSize > $maxFileBytes
                    ? ['theme_file_too_large']
                    : (($readDecision['allowed'] ?? false) ? [] : [(string) ($readDecision['reason'] ?? 'theme_read_blocked')]),
            ],
            'capabilities' => [
                'phpLint' => $validator ? $validator->php_lint_available() : false,
                'atomicRename' => is_writable(dirname($actualPath)),
                'backup' => class_exists('DigitalAfarin_Theme_Backups'),
                'httpQa' => function_exists('wp_remote_get'),
            ],
        ];
    }

    public function read(string $relativePath) {
        $decision = $this->policy->can_read($relativePath);
        if (!($decision['allowed'] ?? false)) {
            return $this->error('digitalafarin_theme_read_blocked', 'Theme file read is blocked by policy.', 403, [
                'reason' => $decision['reason'] ?? 'theme_read_blocked',
            ]);
        }
        $path = $decision['absolutePath'];
        $size = filesize($path);
        $maxFileBytes = (int) ($this->policy->policy()['maxFileBytes'] ?? 1048576);
        if ($size !== false && $size > $maxFileBytes) {
            return $this->error('digitalafarin_theme_file_too_large', 'Theme file exceeds the configured safe read/write size limit.', 413, [
                'sizeBytes' => $size,
                'maxFileBytes' => $maxFileBytes,
                'zipFallbackRecommended' => true,
            ]);
        }
        $content = file_get_contents($path);
        if ($content === false) {
            return $this->error('digitalafarin_theme_read_failed', 'Theme file could not be read.', 500);
        }
        return [
            'relativePath' => $decision['relativePath'],
            'themeRoot' => $decision['themeRoot'],
            'sizeBytes' => strlen($content),
            'modifiedAt' => filemtime($path) ?: 0,
            'sha256' => hash('sha256', $content),
            'content' => $content,
        ];
    }

    private function resolve_url_to_id(string $value): int {
        $value = trim($value);
        if ($value === '') return 0;
        if (str_starts_with($value, '/')) {
            $value = function_exists('home_url') ? home_url($value) : $value;
        }
        if (function_exists('wp_parse_url') && function_exists('home_url')) {
            $targetHost = (string) wp_parse_url($value, PHP_URL_HOST);
            $homeHost = (string) wp_parse_url(home_url('/'), PHP_URL_HOST);
            if ($targetHost !== '' && $homeHost !== '' && strcasecmp($targetHost, $homeHost) !== 0) return 0;
        }
        return function_exists('url_to_postid') ? (int) url_to_postid($value) : 0;
    }

    private function resolve_template_path(object $post, string $assignedSlug): string {
        if ($assignedSlug !== '' && $assignedSlug !== 'default' && function_exists('locate_template')) {
            $located = locate_template([$assignedSlug], false, false);
            if (is_string($located) && $located !== '') return $located;
        }

        $templates = [];
        $slug = (string) ($post->post_name ?? '');
        if ($slug !== '') $templates[] = 'page-' . $slug . '.php';
        $templates[] = 'page-' . (int) $post->ID . '.php';
        $templates[] = 'page.php';

        if (function_exists('get_query_template')) {
            $page = get_query_template('page', $templates);
            if (is_string($page) && $page !== '') return $page;
            $singular = get_query_template('singular', ['singular.php']);
            if (is_string($singular) && $singular !== '') return $singular;
            $index = get_query_template('index', ['index.php']);
            if (is_string($index) && $index !== '') return $index;
        }
        return '';
    }

    private function describe_actual_template(string $actualPath): ?array {
        $actual = realpath($actualPath);
        if ($actual === false) return null;
        $roots = [
            'stylesheet' => function_exists('get_stylesheet_directory') ? get_stylesheet_directory() : '',
            'template' => function_exists('get_template_directory') ? get_template_directory() : '',
        ];
        foreach ($roots as $kind => $root) {
            if (!$root) continue;
            $rootReal = realpath($root);
            if ($rootReal === false) continue;
            $rootPrefix = rtrim(str_replace('\\', '/', $rootReal), '/') . '/';
            $candidate = str_replace('\\', '/', $actual);
            if (str_starts_with($candidate, $rootPrefix)) {
                return ['themeRoot' => $kind, 'relativePath' => substr($candidate, strlen($rootPrefix))];
            }
        }
        return null;
    }

    private function template_assignments(string $assignedSlug, string $relativePath, int $pageId): array {
        $base = basename($relativePath);
        $pageSpecific = preg_match('/^page-(?:\d+|[^\/]+)\.php$/i', $base) === 1 && !in_array($base, ['page.php'], true);
        if ($pageSpecific) return ['sharedTemplate' => false, 'pageIds' => [$pageId]];

        if ($assignedSlug !== '' && $assignedSlug !== 'default' && function_exists('get_posts')) {
            $ids = get_posts([
                'post_type' => 'page',
                'post_status' => ['publish', 'draft', 'pending', 'private', 'future'],
                'fields' => 'ids',
                'posts_per_page' => -1,
                'meta_key' => '_wp_page_template',
                'meta_value' => $assignedSlug,
                'no_found_rows' => true,
            ]);
            $ids = array_values(array_unique(array_map('intval', is_array($ids) ? $ids : [])));
            if (!$ids) $ids = [$pageId];
            return ['sharedTemplate' => count($ids) > 1, 'pageIds' => $ids];
        }

        return ['sharedTemplate' => true, 'pageIds' => [$pageId]];
    }

    private function error(string $code, string $message, int $status, array $data = []) {
        if (class_exists('WP_Error')) return new WP_Error($code, $message, array_merge(['status' => $status], $data));
        return ['error' => true, 'code' => $code, 'message' => $message, 'status' => $status] + $data;
    }
}
