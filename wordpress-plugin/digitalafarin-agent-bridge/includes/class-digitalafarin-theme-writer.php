<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_Writer {
    private DigitalAfarin_Theme_Policy $policy;
    private DigitalAfarin_Theme_Validator $validator;
    private DigitalAfarin_Theme_Backup_Store $backups;
    private $qaRunner;

    public function __construct(
        ?DigitalAfarin_Theme_Policy $policy = null,
        ?DigitalAfarin_Theme_Validator $validator = null,
        ?DigitalAfarin_Theme_Backup_Store $backups = null,
        ?callable $qaRunner = null
    ) {
        $this->policy = $policy ?? DigitalAfarin_Theme_Policy::get();
        $this->validator = $validator ?? new DigitalAfarin_Theme_Validator($this->policy);
        $this->backups = $backups ?? new DigitalAfarin_Theme_Backups();
        $this->qaRunner = $qaRunner;
    }

    public function preview(array $input) {
        return $this->validator->validate_replacement(
            (string) ($input['relativePath'] ?? ''),
            (string) ($input['replacementContent'] ?? ''),
            (string) ($input['expectedHash'] ?? '')
        );
    }

    public function write(array $input) {
        $relativePath = (string) ($input['relativePath'] ?? '');
        $expectedHash = strtolower((string) ($input['expectedHash'] ?? ''));
        $proposedHash = strtolower((string) ($input['proposedHash'] ?? ''));
        $content = (string) ($input['replacementContent'] ?? '');
        $pageId = isset($input['pageId']) ? (int) $input['pageId'] : null;
        $pageUrl = (string) ($input['pageUrl'] ?? '');
        $qaNeedles = array_values(array_slice(array_map('strval', is_array($input['qaNeedles'] ?? null) ? $input['qaNeedles'] : []), 0, 20));

        $preview = $this->preview([
            'relativePath' => $relativePath,
            'replacementContent' => $content,
            'expectedHash' => $expectedHash,
        ]);
        if ($this->is_error($preview)) return $preview;
        if (!($preview['eligible'] ?? false)) return ['written' => false] + $preview;
        if (!preg_match('/^[a-f0-9]{64}$/', $proposedHash) || !hash_equals($preview['proposedHash'], $proposedHash)) {
            return $this->error('digitalafarin_proposed_hash_mismatch', 'Proposed hash does not match previewed replacement.', 409);
        }

        $decision = $this->policy->can_write($relativePath);
        if (!($decision['allowed'] ?? false)) {
            return $this->error('digitalafarin_theme_write_blocked', 'Theme file write is blocked by policy.', 403, [
                'reason' => $decision['reason'] ?? 'theme_write_blocked',
                'zipFallbackRecommended' => true,
            ]);
        }
        $path = $decision['absolutePath'];
        $original = file_get_contents($path);
        if ($original === false) return $this->error('digitalafarin_theme_read_failed', 'Theme file could not be read before write.', 500);
        $originalHash = hash('sha256', $original);
        if (!hash_equals($expectedHash, $originalHash)) {
            return $this->error('theme_template_changed', 'Template changed after preview.', 409, ['currentHash' => $originalHash]);
        }

        $operationId = $this->uuid();
        try {
            $backupId = $this->backups->create([
                'theme_stylesheet' => $this->theme_stylesheet(),
                'relative_path' => $decision['relativePath'],
                'page_id' => $pageId,
                'operation_id' => $operationId,
                'original_hash' => $originalHash,
                'replacement_hash' => $proposedHash,
                'original_content' => $original,
            ]);
        } catch (Throwable $error) {
            return $this->error('digitalafarin_theme_backup_failed', 'Theme backup could not be created; production file was not changed.', 500);
        }

        $replace = $this->atomic_replace($path, $content, $originalHash, $proposedHash);
        if ($this->is_error($replace)) return $replace;

        $qa = $this->run_qa($pageUrl, $qaNeedles);
        $rolledBack = false;
        $rollback = null;
        if (!($qa['passed'] ?? false) && (bool) $this->policy->policy()['autoRollbackOnQaFailure']) {
            $rollback = $this->atomic_replace($path, $original, $proposedHash, $originalHash);
            $rolledBack = !$this->is_error($rollback);
            if ($rolledBack) {
                $qa['rollbackQa'] = $this->run_qa($pageUrl, []);
            }
        }

        if (($qa['passed'] ?? false) && !$rolledBack) {
            $this->backups->trim(
                $this->theme_stylesheet(),
                $decision['relativePath'],
                (int) $this->policy->policy()['backupRetentionPerFile']
            );
        }

        return [
            'written' => !$rolledBack,
            'operationId' => $operationId,
            'backupId' => $backupId,
            'relativePath' => $decision['relativePath'],
            'previousHash' => $originalHash,
            'currentHash' => $rolledBack ? $originalHash : $proposedHash,
            'qa' => $qa,
            'rolledBack' => $rolledBack,
            'rollbackError' => $rollback !== null && $this->is_error($rollback) ? $this->error_code($rollback) : null,
            'zipFallbackRecommended' => false,
        ];
    }

    public function list_backups(?string $relativePath = null, int $limit = 50): array {
        return $this->backups->list($this->theme_stylesheet(), $relativePath, $limit);
    }

    public function restore(string $backupId, string $expectedCurrentHash) {
        $backup = $this->backups->get($backupId);
        if (!$backup) return $this->error('digitalafarin_theme_backup_not_found', 'Theme backup not found.', 404);
        if ((string) ($backup['theme_stylesheet'] ?? '') !== $this->theme_stylesheet()) {
            return $this->error('digitalafarin_theme_backup_theme_mismatch', 'Backup belongs to a different active theme.', 409);
        }
        $relativePath = (string) ($backup['relative_path'] ?? '');
        $decision = $this->policy->can_write($relativePath);
        if (!($decision['allowed'] ?? false)) {
            return $this->error('digitalafarin_theme_restore_blocked', 'Theme restore is blocked by current policy.', 403, [
                'reason' => $decision['reason'] ?? 'theme_restore_blocked',
            ]);
        }
        $path = $decision['absolutePath'];
        $current = file_get_contents($path);
        if ($current === false) return $this->error('digitalafarin_theme_read_failed', 'Current theme file could not be read.', 500);
        $currentHash = hash('sha256', $current);
        if (!hash_equals(strtolower($expectedCurrentHash), strtolower($currentHash))) {
            return $this->error('theme_template_changed', 'Template changed before restore.', 409, ['currentHash' => $currentHash]);
        }
        $restoreContent = (string) ($backup['original_content'] ?? '');
        $restoreHash = hash('sha256', $restoreContent);
        $operationId = $this->uuid();
        try {
            $newBackupId = $this->backups->create([
                'theme_stylesheet' => $this->theme_stylesheet(),
                'relative_path' => $relativePath,
                'page_id' => isset($backup['page_id']) ? (int) $backup['page_id'] : null,
                'operation_id' => $operationId,
                'original_hash' => $currentHash,
                'replacement_hash' => $restoreHash,
                'original_content' => $current,
            ]);
        } catch (Throwable $error) {
            return $this->error('digitalafarin_theme_backup_failed', 'Current version could not be backed up before restore.', 500);
        }
        $replace = $this->atomic_replace($path, $restoreContent, $currentHash, $restoreHash);
        if ($this->is_error($replace)) return $replace;
        $this->backups->mark_restored($backupId, $operationId);
        $this->backups->trim(
            $this->theme_stylesheet(),
            $relativePath,
            (int) $this->policy->policy()['backupRetentionPerFile']
        );
        return [
            'restored' => true,
            'operationId' => $operationId,
            'restoredBackupId' => $backupId,
            'safetyBackupId' => $newBackupId,
            'relativePath' => $relativePath,
            'previousHash' => $currentHash,
            'currentHash' => $restoreHash,
        ];
    }

    private function atomic_replace(string $path, string $content, string $expectedCurrentHash, string $expectedNewHash) {
        $currentHash = hash_file('sha256', $path);
        if ($currentHash === false || !hash_equals(strtolower($expectedCurrentHash), strtolower($currentHash))) {
            return $this->error('theme_template_changed', 'Template changed before atomic replacement.', 409, ['currentHash' => $currentHash ?: null]);
        }
        $dir = dirname($path);
        if (!is_writable($dir)) {
            return $this->error('digitalafarin_atomic_write_unavailable', 'Theme directory is not writable for same-directory atomic replacement.', 409, ['zipFallbackRecommended' => true]);
        }
        $tmp = tempnam($dir, '.digitalafarin-theme-');
        if ($tmp === false) {
            return $this->error('digitalafarin_atomic_write_unavailable', 'Could not create same-directory temporary file.', 409, ['zipFallbackRecommended' => true]);
        }
        try {
            if (file_put_contents($tmp, $content, LOCK_EX) === false) {
                return $this->error('digitalafarin_theme_temp_write_failed', 'Could not write temporary theme file.', 500);
            }
            $permissions = @fileperms($path);
            if ($permissions !== false) @chmod($tmp, $permissions & 0777);
            $lint = $this->validator->lint_file($tmp);
            if (!($lint['available'] ?? false)) {
                return $this->error('php_lint_unavailable', 'PHP syntax validation is unavailable.', 409, ['zipFallbackRecommended' => true]);
            }
            if (!($lint['valid'] ?? false)) {
                return $this->error('php_syntax_invalid', 'Replacement PHP failed syntax validation.', 422, ['lint' => $lint]);
            }
            $tempHash = hash_file('sha256', $tmp);
            if ($tempHash === false || !hash_equals(strtolower($expectedNewHash), strtolower($tempHash))) {
                return $this->error('digitalafarin_theme_temp_hash_mismatch', 'Temporary file hash does not match previewed replacement.', 409);
            }
            if (!@rename($tmp, $path)) {
                return $this->error('digitalafarin_atomic_rename_failed', 'Atomic rename failed; production file was not replaced.', 500, ['zipFallbackRecommended' => true]);
            }
            $tmp = '';
            $productionHash = hash_file('sha256', $path);
            if ($productionHash === false || !hash_equals(strtolower($expectedNewHash), strtolower($productionHash))) {
                return $this->error('digitalafarin_production_hash_mismatch', 'Production file hash verification failed after replacement.', 500);
            }
            return ['replaced' => true, 'currentHash' => $productionHash, 'lint' => $lint];
        } finally {
            if ($tmp !== '' && is_file($tmp)) @unlink($tmp);
        }
    }

    private function run_qa(string $pageUrl, array $needles): array {
        if ($pageUrl === '') return ['passed' => true, 'skipped' => true, 'status' => null, 'missingNeedles' => []];
        if ($this->qaRunner) {
            $raw = ($this->qaRunner)($pageUrl);
        } elseif (function_exists('wp_remote_get')) {
            $response = wp_remote_get($pageUrl, ['timeout' => 12, 'redirection' => 3, 'user-agent' => 'DigitalAfarin-Agent-Bridge/Theme-QA']);
            if (function_exists('is_wp_error') && is_wp_error($response)) {
                return ['passed' => false, 'status' => null, 'error' => $response->get_error_message(), 'missingNeedles' => $needles];
            }
            $raw = [
                'status' => function_exists('wp_remote_retrieve_response_code') ? (int) wp_remote_retrieve_response_code($response) : 0,
                'body' => function_exists('wp_remote_retrieve_body') ? (string) wp_remote_retrieve_body($response) : '',
            ];
        } else {
            return ['passed' => false, 'status' => null, 'error' => 'http_qa_unavailable', 'missingNeedles' => $needles];
        }
        $status = (int) ($raw['status'] ?? 0);
        $body = (string) ($raw['body'] ?? '');
        $missing = [];
        foreach ($needles as $needle) if ($needle !== '' && !str_contains($body, $needle)) $missing[] = $needle;
        return [
            'passed' => $status >= 200 && $status < 300 && $body !== '' && !$missing,
            'status' => $status,
            'bodyBytes' => strlen($body),
            'missingNeedles' => $missing,
            'error' => $raw['error'] ?? null,
        ];
    }

    private function theme_stylesheet(): string {
        return function_exists('get_stylesheet') ? (string) get_stylesheet() : 'unknown';
    }

    private function uuid(): string {
        if (function_exists('wp_generate_uuid4')) return wp_generate_uuid4();
        $data = random_bytes(16);
        $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
        $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
    }

    private function is_error($value): bool {
        return class_exists('WP_Error') && $value instanceof WP_Error;
    }

    private function error_code($value): ?string {
        return $this->is_error($value) && method_exists($value, 'get_error_code') ? (string) $value->get_error_code() : null;
    }

    private function error(string $code, string $message, int $status, array $data = []) {
        if (class_exists('WP_Error')) return new WP_Error($code, $message, array_merge(['status' => $status], $data));
        return ['error' => true, 'code' => $code, 'message' => $message, 'status' => $status] + $data;
    }
}
