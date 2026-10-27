# Safe Theme Template Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let DigitalAfarin SEO agents safely discover, read, preview, update, QA, back up, and restore allowlisted PHP pillar templates in the active WordPress theme, while preserving the existing Page SEO path and falling back to ZIP editing whenever direct production writes are not demonstrably safe.

**Architecture:** Keep WordPress filesystem enforcement inside Agent Bridge, not MCP. Split the new Bridge code into focused theme-policy, template-resolution, preview/write, backup, and REST units; MCP only exposes typed tools over those Bridge routes. The Dashboard configures per-site policy and never gives the SEO agent permission to expand its own allowlist.

**Tech Stack:** WordPress 6.5+, PHP 8.1+, WordPress REST API + Application Passwords, Node.js 20+, TypeScript 5.9, MCP SDK, Zod, Next.js dashboard, PostgreSQL dashboard DB, WordPress options/custom backup table.

**Spec:** `docs/superpowers/specs/2026-09-06-theme-template-automation-design.md`

## Global Constraints

- Target sites are DigitalAfarin-owned, custom-coded WordPress sites; Elementor/page builders are not the source of truth for pillar templates.
- Theme source reads are limited to active stylesheet/parent-theme roots and `.php` files in v1.
- Theme source writes require `manage_options` plus Bridge policy approval; MCP cannot modify policy.
- `functions.php`, `header.php`, `footer.php`, and `index.php` are hard-denied for direct write in v1.
- Direct production write requires an allowlisted path, matching `expectedHash`, bounded size, PHP syntax validation, backup creation, temp-file write, hash verification, atomic rename, and HTTP QA.
- If any mandatory safety gate is unavailable or ambiguous, return `zipFallbackRecommended=true` and do not write production code.
- Existing Page SEO/Yoast/Rank Math tools remain the source of truth for title/meta/canonical/noindex; Theme Automation does not duplicate SEO metadata.
- No shell, arbitrary PHP execution, plugin/core editing, `wp-config.php`, `.htaccess`, Nginx, or generic filesystem tools are introduced.

---

## File Structure

### Bridge
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php` — plugin bootstrap/version/route registration only.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-policy.php` — policy normalization, allowlist, hard-deny, active-theme-root path checks.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-resolver.php` — Page/URL resolution to the actual active-theme PHP template and shared-template impact metadata.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-validator.php` — SHA-256, UTF-8/size checks, PHP lint capability and lint execution.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-backups.php` — schema versioning, backup persistence/list/restore metadata and retention.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-writer.php` — preview, temp-file write, atomic replacement, HTTP QA, auto rollback.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-rest.php` — REST routes and capability checks.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/tests/theme-automation-test.php` — dependency-light PHP behavior tests with WordPress stubs/temp files for path/policy/hash/write primitives.
- Create: `wordpress-plugin/digitalafarin-agent-bridge/tests/run.php` — test runner used by CI/VPS acceptance.

### MCP
- Create: `src/theme-template-client.ts` — typed Bridge REST client and error normalization.
- Create: `src/theme-template-tools.ts` — seven agent-facing MCP tools.
- Create: `src/theme-template-client.test.ts` — request/response/guard behavior tests.
- Modify: `src/server-with-gsc.ts` — register Theme Template tools.
- Modify: `package.json` — bump version and keep test command covering new TS tests.
- Modify: `src/index.ts` — health version bump.

### Dashboard
- Create: `dashboard/lib/theme-automation.ts` — Bridge client for status/policy reads and admin-only policy writes.
- Create: `dashboard/app/sites/[siteId]/theme-automation/page.tsx` — per-site policy/status/audit UI.
- Create: `dashboard/app/sites/[siteId]/theme-automation/actions.ts` — authenticated server actions for policy updates and capability tests.
- Modify: `dashboard/app/sites/page.tsx` — link each site to Theme Automation settings.
- Modify: `dashboard/app/audit/page.tsx` — human labels/details for theme events.
- Modify: `dashboard/app/globals.css` or create a route-local CSS file — policy/editor status layout.

### Docs / deploy
- Modify: `README.md` — feature, security boundary, ZIP fallback, supported hosting requirements.
- Modify: `deploy/update-server.sh` — run Bridge PHP test harness when PHP is available and verify MCP health version.

---

### Task 1: Theme policy and safe path boundary

**Files:**
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-policy.php`
- Create: `wordpress-plugin/digitalafarin-agent-bridge/tests/theme-automation-test.php`
- Create: `wordpress-plugin/digitalafarin-agent-bridge/tests/run.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php`

**Interfaces:**
- Produces: `DigitalAfarin_Theme_Policy::get()`, `normalize(array $raw): array`, `resolve_active_theme_file(string $relative): array|WP_Error`, `can_read(string $relative): array`, `can_write(string $relative): array`.
- Later tasks rely on normalized policy keys: `enabled`, `fullFileWriteEnabled`, `allowedFiles`, `allowedDirectories`, `maxFileBytes`, `backupRetentionPerFile`, `autoRollbackOnQaFailure`.

- [ ] **Step 1: Write failing tests for hard-deny, traversal, symlink escape, allowlisted file, allowlisted directory, and disabled-write policy**

```php
$policy = new DigitalAfarin_Theme_Policy([
    'enabled' => true,
    'fullFileWriteEnabled' => true,
    'allowedFiles' => ['templates/pillar-loan.php'],
    'allowedDirectories' => ['template-parts/pillars/'],
]);
assert_true($policy->can_write('templates/pillar-loan.php')['allowed']);
assert_false($policy->can_write('functions.php')['allowed']);
assert_false($policy->can_write('../wp-config.php')['allowed']);
```

- [ ] **Step 2: Run the test harness and verify RED**

Run:
```bash
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
```
Expected: FAIL because `DigitalAfarin_Theme_Policy` does not exist.

- [ ] **Step 3: Implement policy normalization and canonical active-theme-root checking**

Key behavior:
```php
private const HARD_DENY = ['functions.php', 'header.php', 'footer.php', 'index.php'];

public function can_write(string $relative): array {
    if (!$this->policy['enabled'] || !$this->policy['fullFileWriteEnabled']) {
        return ['allowed' => false, 'reason' => 'theme_write_disabled'];
    }
    // Canonicalize against stylesheet/template roots, enforce .php,
    // reject hard-deny and paths outside roots, then check exact file/dir allowlist.
}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:
```bash
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
```
Expected: all Task 1 assertions PASS.

- [ ] **Step 5: Wire includes into plugin bootstrap and bump Bridge schema/version constant only after tests are green**

- [ ] **Step 6: Commit**

```bash
git add wordpress-plugin/digitalafarin-agent-bridge
git commit -m "feat: add safe theme automation policy boundary"
```

---

### Task 2: Template discovery and source read

**Files:**
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-resolver.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/tests/theme-automation-test.php`
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-rest.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php`

**Interfaces:**
- Produces: `DigitalAfarin_Theme_Resolver::resolve(array $input): array|WP_Error` and `read(string $relativePath): array|WP_Error`.
- Resolve output must include `page`, `theme`, `template`, `capabilities` exactly as the spec describes.
- REST routes added in this task: `GET /theme/status`, `POST /theme/resolve-template`, `GET /theme/file`.

- [ ] **Step 1: Add failing tests for page-specific template, custom assigned template, generic shared template, non-page URL, and hash-bearing read response**

```php
$result = $resolver->resolve(['pageId' => 123]);
assert_same('templates/pillar-property-loan.php', $result['template']['relativePath']);
assert_same(1, $result['template']['assignedPageCount']);
assert_false($result['template']['sharedTemplate']);
```

- [ ] **Step 2: Run tests and verify RED**

Run:
```bash
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
```
Expected: resolver assertions fail because no resolver exists.

- [ ] **Step 3: Implement Page/URL resolution using WordPress APIs**

Required WordPress calls:
```php
get_post($page_id);
get_page_template_slug($page_id);
get_page_template();
wp_get_theme();
```
For URL input, resolve same-site URL/path to a Page ID and reject `post_type !== 'page'` with a structured content-type result instead of pretending it is a Page.

- [ ] **Step 4: Implement shared-template impact detection**

Behavior:
- `page-{id}.php` / `page-{slug}.php` => page-specific.
- custom template assigned to one Page => `assignedPageCount=1`.
- same custom template assigned to multiple Pages => list/count affected Page IDs.
- generic hierarchy fallback => `sharedTemplate=true` and direct write blocked by default.

- [ ] **Step 5: Add REST routes and capability gates**

```php
'read/discovery' => current_user_can('edit_theme_options')
```
Return source, `sha256`, `sizeBytes`, `modifiedAt`, and policy decision; never return absolute filesystem paths.

- [ ] **Step 6: Run tests and PHP syntax check**

```bash
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
php -l wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php
php -l wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-resolver.php
php -l wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-rest.php
```
Expected: PASS / `No syntax errors detected`.

- [ ] **Step 7: Commit**

```bash
git add wordpress-plugin/digitalafarin-agent-bridge
git commit -m "feat: resolve and read active theme pillar templates"
```

---

### Task 3: Preview, stale-hash protection, and PHP validation

**Files:**
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-validator.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-rest.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/tests/theme-automation-test.php`

**Interfaces:**
- Produces: `hash_file_bytes(string $path): string`, `validate_replacement(string $path, string $content, string $expectedHash): array|WP_Error`, `lint_file(string $tempPath): array`.
- REST route: `POST /theme/file/preview`.

- [ ] **Step 1: Add failing tests for matching hash, stale hash, oversize content, non-UTF8 content, lint unavailable, lint failure, and successful preview**

```php
$preview = $validator->validate_replacement($path, "<?php echo 'new';", $current_hash);
assert_true($preview['eligible']);
assert_not_same($current_hash, $preview['proposedHash']);
```

- [ ] **Step 2: Run tests and verify RED**

- [ ] **Step 3: Implement SHA-256 and replacement checks**

On stale content return:
```php
new WP_Error('theme_template_changed', 'Template changed after it was read.', ['status' => 409]);
```

- [ ] **Step 4: Implement compile-only PHP lint capability**

Preferred behavior:
- detect whether PHP CLI lint is safely available;
- lint a temporary file using `php -l` without evaluating template code;
- if unavailable, return `php_lint_unavailable` and `zipFallbackRecommended=true`.

Do not introduce a generic command endpoint; command construction is fixed internally and accepts only the temporary file path created by Bridge.

- [ ] **Step 5: Produce bounded preview metadata**

Return:
```json
{
  "currentHash":"...",
  "proposedHash":"...",
  "sizeDelta":321,
  "lineSummary":{"added":12,"removed":5,"changed":9},
  "lint":{"available":true,"valid":true},
  "eligible":true,
  "blockReasons":[],
  "zipFallbackRecommended":false
}
```
The diff payload must be bounded; never return an unbounded second copy of a huge file.

- [ ] **Step 6: Run tests and syntax checks**

- [ ] **Step 7: Commit**

```bash
git add wordpress-plugin/digitalafarin-agent-bridge
git commit -m "feat: preview theme template rewrites safely"
```

---

### Task 4: Backup storage, atomic write, QA, rollback, and restore

**Files:**
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-backups.php`
- Create: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-writer.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-rest.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/tests/theme-automation-test.php`

**Interfaces:**
- Produces: `create_backup(...)`, `list_backups(...)`, `restore_backup(...)`, `write(...)`.
- REST routes: `POST /theme/file/update`, `GET /theme/backups`, `POST /theme/backups/{id}/restore`.

- [ ] **Step 1: Add failing tests using a temporary theme directory for successful atomic write, stale write refusal, lint failure before rename, QA failure with rollback, restore creating a new backup, and retention trimming**

```php
$result = $writer->write([
    'relativePath' => 'templates/pillar.php',
    'expectedHash' => $old_hash,
    'proposedHash' => hash('sha256', $replacement),
    'replacementContent' => $replacement,
    'pageUrl' => 'https://example.test/pillar/',
    'qaNeedles' => ['Expected H1'],
]);
assert_true($result['written']);
```

- [ ] **Step 2: Run tests and verify RED**

- [ ] **Step 3: Add backup table schema migration**

Create `${wpdb->prefix}digitalafarin_theme_backups` with the exact fields from the spec. Call schema upgrade from normal plugin bootstrap/admin init so upgrading an already-active plugin works without deactivate/reactivate.

- [ ] **Step 4: Implement production write sequence exactly**

```text
recheck hash -> create DB backup -> temp file in same dir -> write/lock -> chmod -> lint temp -> verify proposed hash -> rename -> verify production hash -> HTTP QA
```
Any failure before rename leaves production untouched.

- [ ] **Step 5: Implement HTTP QA and automatic rollback**

Use `wp_remote_get()` with bounded timeout. Required checks: 2xx + non-empty body. Optional `qaNeedles` must all be present. On QA failure with policy enabled, restore the just-created backup using the same validated atomic replacement path and return `rolledBack=true`.

- [ ] **Step 6: Implement manual restore**

Restore must:
- require `manage_options`;
- match active theme stylesheet;
- revalidate current path/policy;
- lint backup content;
- create a backup of the current version before restoring.

- [ ] **Step 7: Run full Bridge test harness and PHP syntax checks**

```bash
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
find wordpress-plugin/digitalafarin-agent-bridge -name '*.php' -print0 | xargs -0 -n1 php -l
```
Expected: all assertions PASS and every PHP file reports no syntax errors.

- [ ] **Step 8: Commit**

```bash
git add wordpress-plugin/digitalafarin-agent-bridge
git commit -m "feat: add reversible atomic theme template writes"
```

---

### Task 5: Bridge theme policy REST surface for Dashboard only

**Files:**
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/includes/class-digitalafarin-theme-rest.php`
- Modify: `wordpress-plugin/digitalafarin-agent-bridge/tests/theme-automation-test.php`

**Interfaces:**
- REST: `GET /theme/policy`, `POST /theme/policy`.
- Policy POST is not exposed through MCP.

- [ ] **Step 1: Add failing tests for default-disabled policy, admin update normalization, hard-deny immutability, invalid directory/path rejection, safe ceiling enforcement, and audit event emission**

- [ ] **Step 2: Run tests and verify RED**

- [ ] **Step 3: Implement policy REST**

Policy update accepts only:
```json
{
  "enabled":true,
  "fullFileWriteEnabled":true,
  "allowedFiles":["templates/pillar.php"],
  "allowedDirectories":["template-parts/pillars/"],
  "maxFileBytes":1048576,
  "backupRetentionPerFile":20,
  "autoRollbackOnQaFailure":true
}
```
Normalize, bound, persist to `digitalafarin_agent_theme_policy`, and audit the change without logging source code.

- [ ] **Step 4: Run Bridge tests**

- [ ] **Step 5: Commit**

```bash
git add wordpress-plugin/digitalafarin-agent-bridge
git commit -m "feat: add admin-managed theme automation policy"
```

---

### Task 6: MCP Theme Template client and tools

**Files:**
- Create: `src/theme-template-client.ts`
- Create: `src/theme-template-tools.ts`
- Create: `src/theme-template-client.test.ts`
- Modify: `src/server-with-gsc.ts`

**Interfaces:**
- Produces MCP tools:
  - `wordpress_get_active_theme`
  - `wordpress_resolve_theme_template`
  - `wordpress_read_theme_template`
  - `wordpress_preview_theme_template_update`
  - `wordpress_update_theme_template`
  - `wordpress_list_theme_backups`
  - `wordpress_restore_theme_backup`

- [ ] **Step 1: Write failing Node tests for route mapping and live-write guards**

```ts
test('preview sends expectedHash and does not use a write endpoint', async () => {
  const client = new ThemeTemplateClient(connection);
  await client.preview({ pageId: 123, relativePath: 'templates/pillar.php', expectedHash: 'a'.repeat(64), replacementContent: '<?php' });
  assert.equal(lastPath, '/wp-json/digitalafarin/v1/theme/file/preview');
});
```

Also test that `update` requires `expectedHash`, `proposedHash`, and replacement content, and that restore carries a current-hash guard.

- [ ] **Step 2: Run focused test and verify RED**

```bash
npm run build
node --test dist/theme-template-client.test.js
```
Expected: FAIL because client/tools do not exist.

- [ ] **Step 3: Implement typed Bridge client**

Normalize Bridge `WP_Error` responses into `WordPressError` while preserving `status`, `code`, `zipFallbackRecommended`, and `blockReasons` when present.

- [ ] **Step 4: Implement seven MCP tools with strict Zod schemas**

Write-tool descriptions must explicitly say they modify production theme code. `wordpress_update_theme_template` must require the hash/proposed hash from preview. No MCP tool for changing policy is created.

- [ ] **Step 5: Register tools in `server-with-gsc.ts`**

```ts
registerThemeTemplateTools(server);
```

- [ ] **Step 6: Run focused and full MCP tests**

```bash
npm test
```
Expected: exit 0, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src
git commit -m "feat: expose safe theme template tools over MCP"
```

---

### Task 7: Per-site Dashboard Theme Automation controls

**Files:**
- Create: `dashboard/lib/theme-automation.ts`
- Create: `dashboard/app/sites/[siteId]/theme-automation/page.tsx`
- Create: `dashboard/app/sites/[siteId]/theme-automation/actions.ts`
- Modify: `dashboard/app/sites/page.tsx`
- Modify: `dashboard/app/audit/page.tsx`
- Modify: `dashboard/app/globals.css` or add route-local CSS.

**Interfaces:**
- Dashboard reads/writes Bridge policy directly using the selected site's encrypted WordPress credentials resolved server-side.
- Ordinary MCP/SEO agent cannot call policy update.

- [ ] **Step 1: Add a small pure-library test for policy payload normalization and redaction**

Create `dashboard/lib/theme-automation.test.ts` if the dashboard test harness supports Node tests; otherwise add it to the root TS test suite as a pure helper module. Assert that secret credentials/source code are never returned in the UI status model.

- [ ] **Step 2: Run test and verify RED**

- [ ] **Step 3: Implement Bridge client helpers**

Functions:
```ts
getThemeAutomationStatus(connection)
getThemeAutomationPolicy(connection)
updateThemeAutomationPolicy(connection, input)
```

- [ ] **Step 4: Implement per-site UI**

Show:
- active theme name/stylesheet/version;
- PHP lint / atomic rename / backup / HTTP QA capability;
- enable/disable Theme Automation;
- enable/disable full-file writes;
- exact allowed files and allowed directories;
- max bytes and backup retention;
- auto rollback toggle;
- immutable hard-deny list;
- current `zipFallbackRecommended` conditions.

Do not expose backup source content in the page.

- [ ] **Step 5: Implement server action validation**

Use Zod to reject traversal, absolute paths, non-`.php` entries, duplicate entries, values beyond global ceilings, and hard-denied files.

- [ ] **Step 6: Add site-list navigation and audit labels**

- [ ] **Step 7: Build dashboard**

```bash
cd dashboard
npm run build
```
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add dashboard
git commit -m "feat: add per-site theme automation controls"
```

---

### Task 8: Audit, versioning, docs, deploy gates, and end-to-end acceptance

**Files:**
- Modify: `README.md`
- Modify: `package.json`
- Modify: `src/index.ts`
- Modify: `deploy/update-server.sh`
- Modify: Bridge plugin header/version and audit hooks.

**Interfaces:**
- Required audit events:
  - `theme.policy_updated`
  - `theme.template_resolved`
  - `theme.template_read`
  - `theme.preview_created`
  - `theme.write_started`
  - `theme.write_succeeded`
  - `theme.write_blocked`
  - `theme.qa_failed`
  - `theme.auto_rollback_succeeded`
  - `theme.auto_rollback_failed`
  - `theme.backup_restored`

- [ ] **Step 1: Add assertions that audit payloads contain hashes/paths/IDs but never replacement or backup source code**

- [ ] **Step 2: Run tests and verify RED if audit filtering is absent**

- [ ] **Step 3: Implement audit event emission and redaction**

Store page ID, relative path, theme stylesheet/version, operation ID, old/new hashes, outcome, block reason, backup ID. Never store template source in audit logs.

- [ ] **Step 4: Bump versions consistently**

Use the next minor version for MCP and Bridge release; update `package.json`, `/health`, plugin header, README, and deploy expected health in one commit.

- [ ] **Step 5: Update deploy script gates**

When PHP is available:
```bash
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
find wordpress-plugin/digitalafarin-agent-bridge -name '*.php' -print0 | xargs -0 -n1 php -l
```
Then build dashboard, run root `npm test`, restart services, and check `/health`.

- [ ] **Step 6: Run full repository verification before PR**

```bash
npm test
cd dashboard && npm run build
cd ..
php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
find wordpress-plugin/digitalafarin-agent-bridge -name '*.php' -print0 | xargs -0 -n1 php -l
git diff --check
```
Expected: all commands exit 0.

- [ ] **Step 7: Staging acceptance on one allowlisted non-critical pillar template**

Acceptance sequence:
```text
get_active_theme
-> resolve_theme_template
-> read_theme_template
-> preview harmless content marker change
-> verify preview/hash/lint
-> update_theme_template
-> verify HTTP 2xx + QA needle
-> read again and confirm new hash
-> list backups
-> restore backup
-> verify original hash/HTTP response
```
Then confirm Page SEO tools still read/write metadata independently.

- [ ] **Step 8: Negative acceptance**

Verify direct writes are blocked for:
```text
functions.php
../wp-config.php
generic page.php when not explicitly allowlisted
stale expectedHash
host without PHP lint
replacement with PHP syntax error
```
Each must leave production content unchanged and return an explicit block reason; unsafe-host cases must recommend ZIP fallback.

- [ ] **Step 9: Request code review, fix all Critical/Important findings, then create PR**

- [ ] **Step 10: Commit final release/docs changes**

```bash
git add README.md package.json src/index.ts deploy/update-server.sh wordpress-plugin dashboard
git commit -m "feat: ship safe theme template automation"
```

---

## Final Acceptance Criteria

The feature is ready to merge only when all of the following are proven by fresh verification:

1. A custom-coded pillar Page can be resolved to its actual active-theme PHP file without exposing absolute server paths.
2. Read returns source + SHA-256; preview never changes production.
3. Agent cannot expand its own allowlist.
4. Hard-denied/global files remain unwritable regardless of policy input.
5. Direct write refuses stale hashes and PHP syntax errors.
6. Every successful write has a recoverable DB backup.
7. Production replacement is atomic or refused.
8. HTTP QA runs after write; configured failures trigger rollback.
9. Manual restore is itself reversible.
10. MCP exposes only the seven bounded Theme Template tools, with no generic filesystem/shell/PHP-execution surface.
11. Dashboard lets an administrator control the policy per site.
12. Existing Page SEO read/write continues independently for Yoast/Rank Math metadata.
13. Unsafe/unsupported hosts return structured ZIP fallback guidance rather than attempting a risky write.
14. Root tests, Dashboard build, Bridge tests, PHP lint, and `git diff --check` all pass immediately before PR/merge.
