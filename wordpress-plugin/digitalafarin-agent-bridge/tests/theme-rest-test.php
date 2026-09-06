<?php

declare(strict_types=1);

if (!class_exists('WP_REST_Server')) {
    class WP_REST_Server { public const READABLE='GET'; public const CREATABLE='POST'; public const EDITABLE='POST'; }
}
if (!class_exists('WP_REST_Request')) {
    class WP_REST_Request implements ArrayAccess {
        public function __construct(private array $params = [], private array $json = []) {}
        public function get_json_params(): array { return $this->json; }
        public function get_param($key) { return $this->params[$key] ?? $this->json[$key] ?? null; }
        public function offsetExists(mixed $offset): bool { return array_key_exists($offset, $this->params) || array_key_exists($offset, $this->json); }
        public function offsetGet(mixed $offset): mixed { return $this->get_param($offset); }
        public function offsetSet(mixed $offset, mixed $value): void { $this->params[$offset] = $value; }
        public function offsetUnset(mixed $offset): void { unset($this->params[$offset], $this->json[$offset]); }
    }
}
$DA_OPTIONS = [];
$DA_ROUTES = [];
function get_option($key, $default = false) { global $DA_OPTIONS; return $DA_OPTIONS[$key] ?? $default; }
function update_option($key, $value, $autoload = null) { global $DA_OPTIONS; $DA_OPTIONS[$key] = $value; return true; }
function current_user_can($cap) { return in_array($cap, ['edit_theme_options','manage_options'], true); }
function register_rest_route($ns, $route, $args) { global $DA_ROUTES; $DA_ROUTES[] = [$ns,$route,$args]; return true; }
function add_action($hook, $callback, $priority = 10, $accepted_args = 1) { return true; }
function rest_ensure_response($value) { return $value; }
function sanitize_text_field($value) { return trim(strip_tags((string)$value)); }
function wp_unslash($value) { return $value; }

require_once __DIR__ . '/../includes/class-digitalafarin-theme-rest.php';

DigitalAfarin_Theme_REST::register_routes();
assert_true(count($DA_ROUTES) >= 8, 'theme REST surface should register status, resolve, file, preview, update, backups, restore, and policy routes');

$validRequest = new WP_REST_Request([], [
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar-property-loan.php'],
    'allowedDirectories' => ['template-parts/pillars/'],
    'maxFileBytes' => 1048576,
    'backupRetentionPerFile' => 20,
    'autoRollbackOnQaFailure' => true,
]);
$updated = DigitalAfarin_Theme_REST::update_policy($validRequest);
assert_false($updated instanceof WP_Error, 'valid policy update should succeed');
assert_true($updated['policy']['enabled']);
assert_same(['templates/pillar-property-loan.php'], $updated['policy']['allowedFiles']);

$invalidRequest = new WP_REST_Request([], [
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['functions.php'],
]);
$invalid = DigitalAfarin_Theme_REST::update_policy($invalidRequest);
assert_true($invalid instanceof WP_Error, 'hard-denied file must be rejected by REST policy update');
assert_same('digitalafarin_invalid_theme_policy', $invalid->get_error_code());

$policyResponse = DigitalAfarin_Theme_REST::get_policy(new WP_REST_Request());
assert_true($policyResponse['policy']['enabled']);
assert_true(in_array('functions.php', $policyResponse['hardDeniedFiles'], true));

echo "Task 5 theme REST policy tests passed\n";
