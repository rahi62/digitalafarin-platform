<?php

declare(strict_types=1);

require_once __DIR__ . '/../includes/class-digitalafarin-theme-audit.php';

$details = DigitalAfarin_Theme_Audit::redact([
    'pageId' => 123,
    'relativePath' => 'templates/pillar.php',
    'oldHash' => str_repeat('a', 64),
    'newHash' => str_repeat('b', 64),
    'replacementContent' => '<?php echo "secret source";',
    'originalContent' => '<?php echo "old source";',
    'nested' => [
        'content' => '<h1>secret</h1>',
        'backupId' => 'backup-1',
        'token' => 'do-not-log',
    ],
]);

assert_same(123, $details['pageId']);
assert_same('templates/pillar.php', $details['relativePath']);
assert_same(str_repeat('a', 64), $details['oldHash']);
assert_false(array_key_exists('replacementContent', $details), 'replacementContent must be redacted');
assert_false(array_key_exists('originalContent', $details), 'originalContent must be redacted');
assert_false(array_key_exists('content', $details['nested']), 'nested content must be redacted');
assert_false(array_key_exists('token', $details['nested']), 'nested token must be redacted');
assert_same('backup-1', $details['nested']['backupId']);

echo "Task 8 theme audit redaction tests passed\n";
