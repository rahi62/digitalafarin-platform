<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_Policy {
    public const OPTION = 'digitalafarin_agent_theme_policy';
    public const MAX_FILE_BYTES_CEILING = 2097152;
    public const MAX_BACKUP_RETENTION = 50;
    private const HARD_DENY = ['functions.php', 'header.php', 'footer.php', 'index.php'];

    private array $policy;
    private array $roots;

    public function __construct(?array $policy = null, ?array $roots = null) {
        $this->policy = self::normalize($policy ?? self::load_option());
        $this->roots = $roots ?? self::default_roots();
    }

    public static function get(): self {
        return new self();
    }

    public static function hard_denied_files(): array {
        return self::HARD_DENY;
    }

    public static function validate_update(array $raw): array {
        $errors = [];
        $rawFiles = $raw['allowedFiles'] ?? [];
        $rawDirs = $raw['allowedDirectories'] ?? [];
        if (!is_array($rawFiles)) {
            $errors[] = 'allowed_files_must_be_array';
            $rawFiles = [];
        }
        if (!is_array($rawDirs)) {
            $errors[] = 'allowed_directories_must_be_array';
            $rawDirs = [];
        }
        foreach ($rawFiles as $value) {
            $value = (string) $value;
            $normalized = self::normalize_relative_path($value, false);
            if ($normalized === null) {
                $errors[] = 'invalid_file:' . $value;
                continue;
            }
            if (self::is_hard_denied($normalized)) $errors[] = 'hard_denied_file:' . $normalized;
        }
        foreach ($rawDirs as $value) {
            $value = (string) $value;
            if (self::normalize_relative_path($value, true) === null) $errors[] = 'invalid_directory:' . $value;
        }
        if (array_key_exists('maxFileBytes', $raw)) {
            $value = (int) $raw['maxFileBytes'];
            if ($value < 1 || $value > self::MAX_FILE_BYTES_CEILING) $errors[] = 'max_file_bytes_out_of_range';
        }
        if (array_key_exists('backupRetentionPerFile', $raw)) {
            $value = (int) $raw['backupRetentionPerFile'];
            if ($value < 1 || $value > self::MAX_BACKUP_RETENTION) $errors[] = 'backup_retention_out_of_range';
        }
        return [
            'valid' => count($errors) === 0,
            'errors' => array_values(array_unique($errors)),
            'policy' => self::normalize($raw),
        ];
    }

    public static function normalize(array $raw): array {
        $files = [];
        foreach (($raw['allowedFiles'] ?? []) as $value) {
            $normalized = self::normalize_relative_path((string) $value, false);
            if ($normalized === null || self::is_hard_denied($normalized)) continue;
            $files[$normalized] = true;
        }

        $dirs = [];
        foreach (($raw['allowedDirectories'] ?? []) as $value) {
            $normalized = self::normalize_relative_path((string) $value, true);
            if ($normalized === null) continue;
            $dirs[$normalized] = true;
        }

        $maxBytes = (int) ($raw['maxFileBytes'] ?? 1048576);
        $maxBytes = max(1, min(self::MAX_FILE_BYTES_CEILING, $maxBytes));
        $retention = (int) ($raw['backupRetentionPerFile'] ?? 20);
        $retention = max(1, min(self::MAX_BACKUP_RETENTION, $retention));

        return [
            'enabled' => (bool) ($raw['enabled'] ?? false),
            'fullFileWriteEnabled' => (bool) ($raw['fullFileWriteEnabled'] ?? false),
            'allowedFiles' => array_keys($files),
            'allowedDirectories' => array_keys($dirs),
            'maxFileBytes' => $maxBytes,
            'backupRetentionPerFile' => $retention,
            'autoRollbackOnQaFailure' => (bool) ($raw['autoRollbackOnQaFailure'] ?? true),
        ];
    }

    public function policy(): array {
        return $this->policy;
    }

    public function can_read(string $relative): array {
        if (!$this->policy['enabled']) {
            return ['allowed' => false, 'reason' => 'theme_automation_disabled'];
        }
        $resolved = $this->resolve_active_theme_file($relative);
        if (!$resolved['allowed']) return $resolved;
        if (!$this->is_allowlisted($resolved['relativePath'])) {
            return ['allowed' => false, 'reason' => 'theme_file_not_allowlisted'];
        }
        return $resolved;
    }

    public function can_write(string $relative): array {
        if (!$this->policy['enabled'] || !$this->policy['fullFileWriteEnabled']) {
            return ['allowed' => false, 'reason' => 'theme_write_disabled'];
        }
        $normalized = self::normalize_relative_path($relative, false);
        if ($normalized === null) {
            return ['allowed' => false, 'reason' => 'invalid_theme_path'];
        }
        if (self::is_hard_denied($normalized)) {
            return ['allowed' => false, 'reason' => 'theme_file_hard_denied'];
        }
        $resolved = $this->resolve_active_theme_file($normalized);
        if (!$resolved['allowed']) return $resolved;
        if (!$this->is_allowlisted($resolved['relativePath'])) {
            return ['allowed' => false, 'reason' => 'theme_file_not_allowlisted'];
        }
        return $resolved;
    }

    public function resolve_active_theme_file(string $relative): array {
        $normalized = self::normalize_relative_path($relative, false);
        if ($normalized === null) {
            return ['allowed' => false, 'reason' => 'invalid_theme_path'];
        }

        foreach ($this->roots as $kind => $root) {
            $rootReal = realpath((string) $root);
            if ($rootReal === false) continue;
            $candidate = $rootReal . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $normalized);
            $candidateReal = realpath($candidate);
            if ($candidateReal === false || !is_file($candidateReal)) continue;
            if (!self::is_inside_root($candidateReal, $rootReal)) {
                return ['allowed' => false, 'reason' => 'theme_path_outside_active_root'];
            }
            return [
                'allowed' => true,
                'reason' => null,
                'relativePath' => $normalized,
                'absolutePath' => $candidateReal,
                'themeRoot' => (string) $kind,
            ];
        }

        return ['allowed' => false, 'reason' => 'theme_file_not_found'];
    }

    private function is_allowlisted(string $relative): bool {
        if (in_array($relative, $this->policy['allowedFiles'], true)) return true;
        foreach ($this->policy['allowedDirectories'] as $dir) {
            if (str_starts_with($relative, $dir)) return true;
        }
        return false;
    }

    private static function is_inside_root(string $candidate, string $root): bool {
        $root = rtrim(str_replace('\\', '/', $root), '/') . '/';
        $candidate = str_replace('\\', '/', $candidate);
        return str_starts_with($candidate . (is_dir($candidate) ? '/' : ''), $root);
    }

    private static function is_hard_denied(string $relative): bool {
        return in_array(strtolower(basename($relative)), self::HARD_DENY, true);
    }

    private static function normalize_relative_path(string $value, bool $directory): ?string {
        $value = trim(str_replace('\\', '/', $value));
        if ($value === '' || str_contains($value, "\0") || str_starts_with($value, '/') || preg_match('/^[A-Za-z]:\//', $value)) {
            return null;
        }
        $parts = array_values(array_filter(explode('/', $value), static fn($part) => $part !== ''));
        if (!$parts) return null;
        foreach ($parts as $part) {
            if ($part === '.' || $part === '..') return null;
        }
        $normalized = implode('/', $parts);
        if ($directory) return rtrim($normalized, '/') . '/';
        if (strtolower(pathinfo($normalized, PATHINFO_EXTENSION)) !== 'php') return null;
        return $normalized;
    }

    private static function load_option(): array {
        if (function_exists('get_option')) {
            $value = get_option(self::OPTION, []);
            return is_array($value) ? $value : [];
        }
        return [];
    }

    private static function default_roots(): array {
        $roots = [];
        if (function_exists('get_stylesheet_directory')) $roots['stylesheet'] = get_stylesheet_directory();
        if (function_exists('get_template_directory')) $roots['template'] = get_template_directory();
        return $roots;
    }
}
