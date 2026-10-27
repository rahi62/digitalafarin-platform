<?php

declare(strict_types=1);

if (!class_exists('WP_Error')) {
    class WP_Error {
        public function __construct(public string $code, public string $message, public array $data = []) {}
        public function get_error_code(): string { return $this->code; }
        public function get_error_data(): array { return $this->data; }
    }
}

$DA_ROOT = sys_get_temp_dir() . '/da-theme-resolver-' . bin2hex(random_bytes(4));
mkdir($DA_ROOT . '/templates', 0777, true);
file_put_contents($DA_ROOT . '/templates/pillar-property-loan.php', "<?php echo '<h1>Pillar</h1>'; ?>");
file_put_contents($DA_ROOT . '/page-shared.php', "<?php echo 'Specific'; ?>");
file_put_contents($DA_ROOT . '/page.php', "<?php echo 'Generic'; ?>");
file_put_contents($DA_ROOT . '/singular.php', "<?php echo 'Singular'; ?>");
file_put_contents($DA_ROOT . '/index.php', "<?php echo 'Index'; ?>");

$DA_POSTS = [
    123 => (object) ['ID' => 123, 'post_type' => 'page', 'post_name' => 'property-loan', 'post_status' => 'publish'],
    124 => (object) ['ID' => 124, 'post_type' => 'page', 'post_name' => 'second-loan', 'post_status' => 'publish'],
    200 => (object) ['ID' => 200, 'post_type' => 'post', 'post_name' => 'validation', 'post_status' => 'publish'],
    300 => (object) ['ID' => 300, 'post_type' => 'page', 'post_name' => 'shared', 'post_status' => 'publish'],
    400 => (object) ['ID' => 400, 'post_type' => 'page', 'post_name' => 'generic', 'post_status' => 'publish'],
];
$DA_TEMPLATE_SLUGS = [123 => 'templates/pillar-property-loan.php', 124 => 'templates/pillar-property-loan.php', 300 => '', 400 => ''];
$DA_URL_IDS = [
    'https://example.test/property-loan/' => 123,
    'https://example.test/validation/' => 200,
];

function get_post($id) { global $DA_POSTS; return $DA_POSTS[(int)$id] ?? null; }
function get_page_template_slug($id) { global $DA_TEMPLATE_SLUGS; return $DA_TEMPLATE_SLUGS[(int)$id] ?? ''; }
function get_stylesheet_directory() { global $DA_ROOT; return $DA_ROOT; }
function get_template_directory() { global $DA_ROOT; return $DA_ROOT; }
function get_stylesheet() { return 'digitalafarin-loans'; }
function is_child_theme() { return false; }
function get_permalink($id) { $post = get_post($id); return $post ? 'https://example.test/' . $post->post_name . '/' : ''; }
function home_url($path = '/') { return 'https://example.test' . (str_starts_with($path, '/') ? $path : '/' . $path); }
function url_to_postid($url) { global $DA_URL_IDS; return $DA_URL_IDS[$url] ?? 0; }
function wp_parse_url($url, $component = -1) { return parse_url($url, $component); }
function wp_get_theme() { return new class { public function get($key) { return ['Name'=>'DigitalAfarin Loans','Version'=>'1.4.0'][$key] ?? ''; } }; }
function locate_template($templates, $load = false, $load_once = true) {
    global $DA_ROOT;
    foreach ((array)$templates as $template) {
        $path = $DA_ROOT . '/' . ltrim($template, '/');
        if (is_file($path)) return $path;
    }
    return '';
}
function get_query_template($type, $templates = []) {
    global $DA_ROOT;
    foreach ((array)$templates as $template) {
        $path = $DA_ROOT . '/' . ltrim($template, '/');
        if (is_file($path)) return $path;
    }
    return '';
}
function get_posts($args = []) {
    global $DA_TEMPLATE_SLUGS;
    $wanted = $args['meta_value'] ?? null;
    $ids = [];
    foreach ($DA_TEMPLATE_SLUGS as $id => $slug) if ($slug === $wanted) $ids[] = (int)$id;
    return $ids;
}

require_once __DIR__ . '/../includes/class-digitalafarin-theme-resolver.php';

$policy = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar-property-loan.php', 'page-shared.php', 'page.php'],
], ['stylesheet' => $DA_ROOT, 'template' => $DA_ROOT]);
$resolver = new DigitalAfarin_Theme_Resolver($policy);

$custom = $resolver->resolve(['pageId' => 123]);
assert_false($custom instanceof WP_Error, 'custom template should resolve');
assert_same('templates/pillar-property-loan.php', $custom['template']['relativePath']);
assert_same(2, $custom['template']['assignedPageCount']);
assert_true($custom['template']['sharedTemplate']);
assert_true($custom['template']['readAllowed']);
assert_true($custom['template']['writeAllowed']);
assert_same(64, strlen($custom['template']['sha256']));

$byUrl = $resolver->resolve(['url' => '/property-loan/']);
assert_false($byUrl instanceof WP_Error, 'same-site path should resolve');
assert_same(123, $byUrl['page']['id']);

$notPage = $resolver->resolve(['url' => '/validation/']);
assert_true($notPage instanceof WP_Error, 'post URL must not be treated as page');
assert_same('digitalafarin_not_a_page', $notPage->get_error_code());
assert_same('post', $notPage->get_error_data()['contentType']);

$specific = $resolver->resolve(['pageId' => 300]);
assert_false($specific instanceof WP_Error, 'page-slug template should resolve');
assert_same('page-shared.php', $specific['template']['relativePath']);
assert_false($specific['template']['sharedTemplate']);

$generic = $resolver->resolve(['pageId' => 400]);
assert_false($generic instanceof WP_Error, 'generic page.php should resolve');
assert_same('page.php', $generic['template']['relativePath']);
assert_true($generic['template']['sharedTemplate']);

$read = $resolver->read('templates/pillar-property-loan.php');
assert_false($read instanceof WP_Error, 'allowlisted template should be readable');
assert_same(hash('sha256', $read['content']), $read['sha256']);
assert_true(str_contains($read['content'], 'Pillar'));

echo "Task 2 theme resolver tests passed\n";
