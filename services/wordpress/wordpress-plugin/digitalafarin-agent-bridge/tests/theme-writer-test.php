<?php

declare(strict_types=1);

require_once __DIR__ . '/../includes/class-digitalafarin-theme-backups.php';
require_once __DIR__ . '/../includes/class-digitalafarin-theme-writer.php';

final class MemoryThemeBackups implements DigitalAfarin_Theme_Backup_Store {
    public array $rows = [];
    public array $trimCalls = [];
    public array $restored = [];
    private int $seq = 0;
    public function create(array $record): string {
        $id = 'backup-' . (++$this->seq);
        $this->rows[$id] = ['id' => $id] + $record;
        return $id;
    }
    public function get(string $id): ?array { return $this->rows[$id] ?? null; }
    public function list(string $themeStylesheet, ?string $relativePath = null, int $limit = 50): array {
        $rows = array_values(array_filter($this->rows, static function(array $row) use ($themeStylesheet, $relativePath): bool {
            if (($row['theme_stylesheet'] ?? '') !== $themeStylesheet) return false;
            return $relativePath === null || ($row['relative_path'] ?? '') === $relativePath;
        }));
        return array_slice(array_reverse($rows), 0, $limit);
    }
    public function mark_restored(string $id, string $restoreOperationId): void { $this->restored[$id] = $restoreOperationId; }
    public function trim(string $themeStylesheet, string $relativePath, int $keep): void { $this->trimCalls[] = [$themeStylesheet, $relativePath, $keep]; }
}

$writerRoot = sys_get_temp_dir() . '/da-theme-writer-' . bin2hex(random_bytes(4));
mkdir($writerRoot . '/templates', 0777, true);
$writerPath = $writerRoot . '/templates/pillar.php';
$oldContent = "<?php echo '<h1>Old</h1>'; ?>\n";
$newContent = "<?php echo '<h1>New</h1>'; ?>\n";
file_put_contents($writerPath, $oldContent);

$writerPolicy = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar.php'],
    'maxFileBytes' => 100000,
    'backupRetentionPerFile' => 5,
    'autoRollbackOnQaFailure' => true,
], ['stylesheet' => $writerRoot, 'template' => $writerRoot]);

$store = new MemoryThemeBackups();
$validator = new DigitalAfarin_Theme_Validator($writerPolicy, static fn(string $path): array => ['available' => true, 'valid' => true, 'output' => []]);
$qa = static fn(string $url): array => ['status' => 200, 'body' => '<html><h1>New</h1></html>'];
$writer = new DigitalAfarin_Theme_Writer($writerPolicy, $validator, $store, $qa);
$oldHash = hash('sha256', $oldContent);
$newHash = hash('sha256', $newContent);
$result = $writer->write([
    'pageId' => 123,
    'pageUrl' => 'https://example.test/property-loan/',
    'relativePath' => 'templates/pillar.php',
    'expectedHash' => $oldHash,
    'proposedHash' => $newHash,
    'replacementContent' => $newContent,
    'qaNeedles' => ['<h1>New</h1>'],
]);
assert_false($result instanceof WP_Error, 'successful write must not error');
assert_true($result['written']);
assert_false($result['rolledBack']);
assert_same($newContent, file_get_contents($writerPath));
assert_same($oldContent, $store->rows[$result['backupId']]['original_content']);
assert_true(count($store->trimCalls) === 1, 'successful write should trim backups');

file_put_contents($writerPath, $oldContent);
$lintCalls = 0;
$flakyValidator = new DigitalAfarin_Theme_Validator($writerPolicy, static function(string $path) use (&$lintCalls): array {
    $lintCalls++;
    return ['available' => true, 'valid' => $lintCalls === 1, 'output' => $lintCalls === 1 ? [] : ['Parse error']];
});
$store2 = new MemoryThemeBackups();
$writer2 = new DigitalAfarin_Theme_Writer($writerPolicy, $flakyValidator, $store2, $qa);
$lintFailure = $writer2->write([
    'pageId' => 123,
    'pageUrl' => 'https://example.test/property-loan/',
    'relativePath' => 'templates/pillar.php',
    'expectedHash' => $oldHash,
    'proposedHash' => $newHash,
    'replacementContent' => $newContent,
]);
assert_true($lintFailure instanceof WP_Error, 'second-stage lint failure must error');
assert_same('php_syntax_invalid', $lintFailure->get_error_code());
assert_same($oldContent, file_get_contents($writerPath));

file_put_contents($writerPath, $oldContent);
$qaCalls = 0;
$qaFailThenRecover = static function(string $url) use (&$qaCalls): array {
    $qaCalls++;
    return $qaCalls === 1
        ? ['status' => 500, 'body' => 'broken']
        : ['status' => 200, 'body' => '<html>old restored</html>'];
};
$store3 = new MemoryThemeBackups();
$writer3 = new DigitalAfarin_Theme_Writer($writerPolicy, $validator, $store3, $qaFailThenRecover);
$rollbackResult = $writer3->write([
    'pageId' => 123,
    'pageUrl' => 'https://example.test/property-loan/',
    'relativePath' => 'templates/pillar.php',
    'expectedHash' => $oldHash,
    'proposedHash' => $newHash,
    'replacementContent' => $newContent,
]);
assert_true($rollbackResult['rolledBack'], 'QA failure must roll back when policy enables it');
assert_false($rollbackResult['written']);
assert_same($oldContent, file_get_contents($writerPath));
assert_same($oldHash, $rollbackResult['currentHash']);

file_put_contents($writerPath, $oldContent);
$store4 = new MemoryThemeBackups();
$writer4 = new DigitalAfarin_Theme_Writer($writerPolicy, $validator, $store4, $qa);
$writeForRestore = $writer4->write([
    'pageId' => 123,
    'pageUrl' => 'https://example.test/property-loan/',
    'relativePath' => 'templates/pillar.php',
    'expectedHash' => $oldHash,
    'proposedHash' => $newHash,
    'replacementContent' => $newContent,
]);
$restore = $writer4->restore($writeForRestore['backupId'], $newHash);
assert_false($restore instanceof WP_Error, 'restore should succeed');
assert_true($restore['restored']);
assert_same($oldContent, file_get_contents($writerPath));
assert_true(isset($store4->rows[$restore['safetyBackupId']]), 'restore must create a safety backup');
assert_true(isset($store4->restored[$writeForRestore['backupId']]), 'restored backup must be marked');

file_put_contents($writerPath, $newContent);
$staleRestore = $writer4->restore($writeForRestore['backupId'], str_repeat('a', 64));
assert_true($staleRestore instanceof WP_Error);
assert_same('theme_template_changed', $staleRestore->get_error_code());
assert_same($newContent, file_get_contents($writerPath));

echo "Task 4 theme writer tests passed\n";
