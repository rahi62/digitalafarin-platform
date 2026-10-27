<?php

declare(strict_types=1);

$validatorRoot = sys_get_temp_dir() . '/da-theme-validator-' . bin2hex(random_bytes(4));
mkdir($validatorRoot . '/templates', 0777, true);
$validatorPath = $validatorRoot . '/templates/pillar.php';
file_put_contents($validatorPath, "<?php echo 'old'; ?>\n");

require_once __DIR__ . '/../includes/class-digitalafarin-theme-validator.php';

$validatorPolicy = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar.php'],
    'maxFileBytes' => 1000,
], ['stylesheet' => $validatorRoot, 'template' => $validatorRoot]);

$validLint = static fn(string $path): array => ['available' => true, 'valid' => true, 'output' => ['No syntax errors detected']];
$validator = new DigitalAfarin_Theme_Validator($validatorPolicy, $validLint);
$oldHash = hash_file('sha256', $validatorPath);
$preview = $validator->validate_replacement('templates/pillar.php', "<?php echo 'new'; ?>\n", $oldHash);
assert_false($preview instanceof WP_Error, 'valid preview should not error');
assert_true($preview['eligible']);
assert_same([], $preview['blockReasons']);
assert_same(64, strlen($preview['proposedHash']));
assert_false($preview['zipFallbackRecommended']);

$stale = $validator->validate_replacement('templates/pillar.php', "<?php echo 'new'; ?>", str_repeat('a', 64));
assert_true($stale instanceof WP_Error, 'stale hash must return WP_Error');
assert_same('theme_template_changed', $stale->get_error_code());

$smallPolicy = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar.php'],
    'maxFileBytes' => 10,
], ['stylesheet' => $validatorRoot, 'template' => $validatorRoot]);
$smallValidator = new DigitalAfarin_Theme_Validator($smallPolicy, $validLint);
$oversize = $smallValidator->validate_replacement('templates/pillar.php', str_repeat('x', 20), $oldHash);
assert_false($oversize['eligible']);
assert_true(in_array('replacement_too_large', $oversize['blockReasons'], true));

$invalidUtf = $validator->validate_replacement('templates/pillar.php', "<?php \xC3\x28", $oldHash);
assert_false($invalidUtf['eligible']);
assert_true(in_array('replacement_not_utf8', $invalidUtf['blockReasons'], true));

$noLint = new DigitalAfarin_Theme_Validator($validatorPolicy, static fn(string $path): array => ['available' => false, 'valid' => false]);
$lintUnavailable = $noLint->validate_replacement('templates/pillar.php', "<?php echo 'new'; ?>", $oldHash);
assert_false($lintUnavailable['eligible']);
assert_true(in_array('php_lint_unavailable', $lintUnavailable['blockReasons'], true));
assert_true($lintUnavailable['zipFallbackRecommended']);

$badLint = new DigitalAfarin_Theme_Validator($validatorPolicy, static fn(string $path): array => ['available' => true, 'valid' => false, 'output' => ['Parse error']]);
$lintInvalid = $badLint->validate_replacement('templates/pillar.php', "<?php if (", $oldHash);
assert_false($lintInvalid['eligible']);
assert_true(in_array('php_syntax_invalid', $lintInvalid['blockReasons'], true));

echo "Task 3 theme validator tests passed\n";
