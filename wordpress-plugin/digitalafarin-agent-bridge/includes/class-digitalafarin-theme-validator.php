<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_Validator {
    private DigitalAfarin_Theme_Policy $policy;
    private $lintRunner;

    public function __construct(?DigitalAfarin_Theme_Policy $policy = null, ?callable $lintRunner = null) {
        $this->policy = $policy ?? DigitalAfarin_Theme_Policy::get();
        $this->lintRunner = $lintRunner;
    }

    public function validate_replacement(string $relativePath, string $content, string $expectedHash) {
        $decision = $this->policy->can_write($relativePath);
        if (!($decision['allowed'] ?? false)) {
            return $this->error('digitalafarin_theme_write_blocked', 'Theme file write is blocked by policy.', 403, [
                'reason' => $decision['reason'] ?? 'theme_write_blocked',
                'zipFallbackRecommended' => true,
            ]);
        }

        $path = $decision['absolutePath'];
        $current = file_get_contents($path);
        if ($current === false) {
            return $this->error('digitalafarin_theme_read_failed', 'Theme file could not be read before preview.', 500);
        }
        $currentHash = hash('sha256', $current);
        if (!preg_match('/^[a-f0-9]{64}$/i', $expectedHash) || !hash_equals(strtolower($currentHash), strtolower($expectedHash))) {
            return $this->error('theme_template_changed', 'Template changed after it was read.', 409, [
                'currentHash' => $currentHash,
                'expectedHash' => $expectedHash,
            ]);
        }

        $blockReasons = [];
        $sizeBytes = strlen($content);
        $maxBytes = (int) $this->policy->policy()['maxFileBytes'];
        if ($sizeBytes > $maxBytes) $blockReasons[] = 'replacement_too_large';
        if (!$this->is_utf8($content)) $blockReasons[] = 'replacement_not_utf8';

        $lint = ['available' => false, 'valid' => false, 'output' => []];
        if (!$blockReasons) {
            $lint = $this->lint_content($content);
            if (!$lint['available']) $blockReasons[] = 'php_lint_unavailable';
            elseif (!$lint['valid']) $blockReasons[] = 'php_syntax_invalid';
        }

        $proposedHash = hash('sha256', $content);
        $summary = $this->line_summary($current, $content);
        $eligible = count($blockReasons) === 0;

        return [
            'relativePath' => $decision['relativePath'],
            'currentHash' => $currentHash,
            'proposedHash' => $proposedHash,
            'currentSizeBytes' => strlen($current),
            'proposedSizeBytes' => $sizeBytes,
            'sizeDelta' => $sizeBytes - strlen($current),
            'lineSummary' => $summary,
            'lint' => $lint,
            'eligible' => $eligible,
            'blockReasons' => $blockReasons,
            'zipFallbackRecommended' => !$eligible,
        ];
    }

    public function lint_content(string $content): array {
        $tmp = tempnam(sys_get_temp_dir(), 'digitalafarin-theme-lint-');
        if ($tmp === false) return ['available' => false, 'valid' => false, 'output' => ['temp_file_unavailable']];
        $phpTmp = $tmp . '.php';
        @rename($tmp, $phpTmp);
        try {
            if (file_put_contents($phpTmp, $content, LOCK_EX) === false) {
                return ['available' => false, 'valid' => false, 'output' => ['temp_write_failed']];
            }
            if ($this->lintRunner) {
                $result = ($this->lintRunner)($phpTmp);
                return $this->normalize_lint_result($result);
            }
            return $this->run_php_lint($phpTmp);
        } finally {
            @unlink($phpTmp);
            @unlink($tmp);
        }
    }

    public function php_lint_available(): bool {
        if ($this->lintRunner) return true;
        return $this->find_php_cli() !== null && $this->function_enabled('exec');
    }

    private function run_php_lint(string $path): array {
        $binary = $this->find_php_cli();
        if ($binary === null || !$this->function_enabled('exec')) {
            return ['available' => false, 'valid' => false, 'output' => []];
        }
        $output = [];
        $status = 1;
        $command = escapeshellarg($binary) . ' -l ' . escapeshellarg($path) . ' 2>&1';
        exec($command, $output, $status);
        return ['available' => true, 'valid' => $status === 0, 'output' => array_slice(array_map('strval', $output), 0, 10)];
    }

    private function normalize_lint_result($result): array {
        if (!is_array($result)) return ['available' => false, 'valid' => false, 'output' => []];
        return [
            'available' => (bool) ($result['available'] ?? true),
            'valid' => (bool) ($result['valid'] ?? false),
            'output' => array_slice(array_map('strval', is_array($result['output'] ?? null) ? $result['output'] : []), 0, 10),
        ];
    }

    private function find_php_cli(): ?string {
        $candidates = [];
        if (defined('PHP_BINARY')) $candidates[] = PHP_BINARY;
        $candidates[] = '/usr/bin/php';
        $candidates[] = '/usr/local/bin/php';
        foreach (array_unique(array_filter($candidates)) as $candidate) {
            if (!is_file($candidate) || !is_executable($candidate)) continue;
            $base = strtolower(basename($candidate));
            if (!str_starts_with($base, 'php') || str_contains($base, 'fpm')) continue;
            return $candidate;
        }
        return null;
    }

    private function function_enabled(string $name): bool {
        if (!function_exists($name)) return false;
        $disabled = array_filter(array_map('trim', explode(',', (string) ini_get('disable_functions'))));
        return !in_array($name, $disabled, true);
    }

    private function is_utf8(string $content): bool {
        if (function_exists('mb_check_encoding')) return mb_check_encoding($content, 'UTF-8');
        return preg_match('//u', $content) === 1;
    }

    private function line_summary(string $before, string $after): array {
        $a = preg_split('/\R/', $before) ?: [];
        $b = preg_split('/\R/', $after) ?: [];
        $prefix = 0;
        $limit = min(count($a), count($b));
        while ($prefix < $limit && $a[$prefix] === $b[$prefix]) $prefix++;
        $suffix = 0;
        while ($suffix < ($limit - $prefix)
            && $a[count($a) - 1 - $suffix] === $b[count($b) - 1 - $suffix]) $suffix++;
        $removed = max(0, count($a) - $prefix - $suffix);
        $added = max(0, count($b) - $prefix - $suffix);
        return ['added' => $added, 'removed' => $removed, 'changed' => min($added, $removed)];
    }

    private function error(string $code, string $message, int $status, array $data = []) {
        if (class_exists('WP_Error')) return new WP_Error($code, $message, array_merge(['status' => $status], $data));
        return ['error' => true, 'code' => $code, 'message' => $message, 'status' => $status] + $data;
    }
}
