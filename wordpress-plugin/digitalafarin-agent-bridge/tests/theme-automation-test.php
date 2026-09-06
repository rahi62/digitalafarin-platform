<?php

declare(strict_types=1);

function assert_true($value, string $message = 'expected true'): void {
    if ($value !== true) throw new RuntimeException($message);
}
function assert_false($value, string $message = 'expected false'): void {
    if ($value !== false) throw new RuntimeException($message);
}
function assert_same($expected, $actual, string $message = ''): void {
    if ($expected !== $actual) throw new RuntimeException($message ?: 'values differ');
}

require_once __DIR__ . '/../includes/class-digitalafarin-theme-policy.php';

$root = sys_get_temp_dir() . '/da-theme-policy-' . bin2hex(random_bytes(4));
$outside = sys_get_temp_dir() . '/da-theme-outside-' . bin2hex(random_bytes(4));
mkdir($root . '/templates', 0777, true);
mkdir($root . '/template-parts/pillars', 0777, true);
mkdir($outside, 0777, true);
file_put_contents($root . '/templates/pillar-loan.php', "<?php echo 'pillar';");
file_put_contents($root . '/template-parts/pillars/faq.php', "<?php echo 'faq';");
file_put_contents($root . '/functions.php', "<?php echo 'no';");
file_put_contents($outside . '/escaped.php', "<?php echo 'escape';");
@symlink($outside . '/escaped.php', $root . '/templates/escaped.php');

$enabled = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar-loan.php'],
    'allowedDirectories' => ['template-parts/pillars/'],
    'maxFileBytes' => 1048576,
    'backupRetentionPerFile' => 20,
    'autoRollbackOnQaFailure' => true,
], ['stylesheet' => $root, 'template' => $root]);

assert_true($enabled->can_write('templates/pillar-loan.php')['allowed'], 'allowlisted file should be writable');
assert_true($enabled->can_write('template-parts/pillars/faq.php')['allowed'], 'allowlisted directory file should be writable');
assert_false($enabled->can_write('functions.php')['allowed'], 'functions.php must be hard denied');
assert_false($enabled->can_write('../wp-config.php')['allowed'], 'traversal must be rejected');
assert_false($enabled->can_write('templates/escaped.php')['allowed'], 'symlink escape must be rejected');
assert_false($enabled->can_write('templates/not-allowed.php')['allowed'], 'non-allowlisted file must be rejected');

$disabled = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => false,
    'allowedFiles' => ['templates/pillar-loan.php'],
], ['stylesheet' => $root, 'template' => $root]);
assert_false($disabled->can_write('templates/pillar-loan.php')['allowed'], 'write switch must block writes');
assert_same('theme_write_disabled', $disabled->can_write('templates/pillar-loan.php')['reason']);

$normalized = DigitalAfarin_Theme_Policy::normalize([
    'enabled' => 1,
    'fullFileWriteEnabled' => 1,
    'allowedFiles' => ['templates/pillar-loan.php', 'templates/pillar-loan.php', '../bad.php', 'header.php'],
    'allowedDirectories' => ['template-parts/pillars', 'template-parts/pillars/'],
    'maxFileBytes' => 99999999,
    'backupRetentionPerFile' => 999,
]);
assert_same(['templates/pillar-loan.php'], $normalized['allowedFiles']);
assert_same(['template-parts/pillars/'], $normalized['allowedDirectories']);
assert_same(DigitalAfarin_Theme_Policy::MAX_FILE_BYTES_CEILING, $normalized['maxFileBytes']);
assert_same(DigitalAfarin_Theme_Policy::MAX_BACKUP_RETENTION, $normalized['backupRetentionPerFile']);

echo "Task 1 theme policy tests passed\n";
