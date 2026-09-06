# Safe Theme Template Automation Design

**Date:** 2026-09-06  
**Status:** Proposed / approved in chat, pending written-spec review  
**Project:** DigitalAfarin WordPress MCP + DigitalAfarin Agent Bridge

## 1. Problem

DigitalAfarin SEO agents can already read/write WordPress Posts and Pages, manage SEO metadata, indexing overrides, media, redirects, and Search Console data. Some important pillar pages on DigitalAfarin-owned sites are different: the WordPress Page exists mainly as the URL/SEO entity, while the visible pillar content and layout are hard-coded in a custom PHP page template.

For these pillars, editing `post_content` is not sufficient. The agent must be able to identify the active theme and the actual PHP template responsible for the pillar, read that source, rewrite the template when needed, and then continue to manage SEO title/meta/canonical/noindex through the existing Page SEO path.

The feature must allow real code changes without turning Agent Bridge into an unrestricted remote file editor.

## 2. Assumptions

- Target sites are DigitalAfarin-owned, custom-coded WordPress sites.
- Elementor or other visual page builders are not the source of truth for these pillar templates.
- Pillar templates are PHP files in the active theme or child theme.
- WordPress Application Password authentication remains the transport authentication mechanism.
- Theme template writes are administrator-level operations and require `manage_options` in addition to Bridge-specific policy checks.
- Existing Page SEO read/write remains the source of truth for Yoast/Rank Math metadata. Theme automation does not duplicate SEO-meta storage.

## 3. Goals

1. Resolve a pillar URL/Page to the actual active-theme PHP template WordPress uses.
2. Read the full source of an approved template file.
3. Preview a replacement before writing it.
4. Permit full-template rewrites only when the site administrator has explicitly enabled and allowlisted the target.
5. Refuse stale writes using a content hash (`expectedHash`).
6. Create a reversible backup before every production write.
7. Validate replacement PHP before production replacement.
8. Replace files atomically when the host supports the required safety gates.
9. Run post-write HTTP QA against the pillar URL and automatically roll back when configured QA fails.
10. Keep an audit trail of theme discovery, previews, writes, failures, rollbacks, and restores.
11. Fall back to the existing "upload theme ZIP -> ChatGPT edits source -> user deploys ZIP" workflow whenever direct writing is not demonstrably safe.
12. Keep the design product-ready for multiple sites without giving ordinary customers arbitrary filesystem access.

## 4. Non-goals for v1

- Arbitrary editing of WordPress core files.
- Arbitrary plugin editing.
- Editing `wp-config.php`, `.htaccess`, Nginx configuration, or server files.
- Installing themes/plugins.
- Exposing a generic shell/command execution tool.
- Direct Git repository synchronization after a production hotfix.
- Automatic refactoring of all files included by a template.
- Safe internal-link search/preview/replace; that remains a separate capability/spec.
- Browser-driven Search Console "Request indexing" automation.

## 5. Recommended architecture

Use a hybrid model:

**Normal path**  
`Page URL -> Page ID -> template resolution -> allowlist/policy -> source read -> preview -> safety validation -> backup -> atomic write -> HTTP QA -> Page SEO update -> GSC inspection`

**Fallback path**  
If any direct-write safety gate is unavailable or ambiguous, Bridge refuses the write and returns a structured `zipFallbackRecommended` result. The user can then provide the current theme ZIP to ChatGPT, ChatGPT edits the source artifact, the user deploys it, and the agent applies Page SEO metadata through the existing MCP tools.

Direct theme writing is therefore an optimization for safe, well-understood templates, not a requirement for every change.

## 6. Security model

### 6.1 Capability gate

Every theme source endpoint requires an authenticated WordPress user.

- Read/discovery: require `edit_theme_options`.
- Preview/write/restore/policy update: require `manage_options`.

WordPress capabilities alone are not sufficient for writes. Bridge also enforces its own theme policy.

### 6.2 Active-theme boundary

Bridge may only resolve files beneath:

- `get_stylesheet_directory()` for the active stylesheet/child theme; or
- `get_template_directory()` for the active parent theme when WordPress resolves the template there.

All requested paths are canonicalized with `realpath()` before reading. A path is rejected if:

- it contains traversal components;
- it resolves outside the active theme roots;
- it resolves through a symlink to a location outside the allowed theme root;
- its extension is not `.php` in v1.

### 6.3 Hard-deny list

The following files are never directly writable in v1, even if an administrator attempts to allowlist them:

- `functions.php`
- `header.php`
- `footer.php`
- `index.php`

The feature is intended for pillar page templates and pillar template parts, not global runtime/bootstrap files.

### 6.4 Site policy

Agent Bridge stores a local WordPress option named `digitalafarin_agent_theme_policy`. Example logical structure:

```json
{
  "enabled": true,
  "fullFileWriteEnabled": true,
  "allowedFiles": [
    "page-property-loan.php",
    "templates/pillar-property-loan.php"
  ],
  "allowedDirectories": [
    "templates/pillars/",
    "template-parts/pillars/"
  ],
  "maxFileBytes": 1048576,
  "backupRetentionPerFile": 20,
  "autoRollbackOnQaFailure": true
}
```

Policy is enforced by the Bridge on the WordPress host. The MCP server cannot bypass it.

The Dashboard may configure this policy through an admin-only Bridge route. The MCP toolset does **not** expose a tool that lets the SEO agent expand its own allowlist.

Default policy after plugin upgrade is disabled for writes.

## 7. Template discovery

### 7.1 Inputs

Discovery accepts either:

- `pageId`, or
- a same-site URL/path which Bridge resolves to a Page ID.

The resolved object must be `post_type=page`. If it resolves to a Post, discovery reports the real content type and refuses to treat it as a theme-backed Page.

### 7.2 Resolution

For a Page:

1. Read `get_page_template_slug($pageId)`.
2. Ask WordPress for the actual page template using the active theme/template hierarchy.
3. Canonicalize the absolute resolved file.
4. Convert it back to a relative path under the stylesheet or parent-template root.
5. Report whether it is a child-theme or parent-theme file.

If a Page uses `default` and WordPress resolves to a generic shared template such as `page.php`, `singular.php`, or `index.php`, direct write is blocked by default and discovery explains why.

### 7.3 Shared-template risk

Discovery reports whether the resolved template is likely shared:

- custom template assigned to more than one Page: include the assignment count;
- generic hierarchy fallback: mark `sharedTemplate=true`;
- page-specific template (`page-{id}.php` or `page-{slug}.php`): mark as page-specific;
- custom template assigned to exactly one Page: mark as single-assignment.

A shared template can be read, but a write requires it to be explicitly allowlisted and the preview response must identify affected Page IDs when those assignments can be determined.

### 7.4 Discovery response

Logical response shape:

```json
{
  "page": {
    "id": 123,
    "url": "https://example.com/property-loan/",
    "slug": "property-loan",
    "status": "publish"
  },
  "theme": {
    "name": "DigitalAfarin Loans",
    "stylesheet": "digitalafarin-loans",
    "version": "1.4.0",
    "childTheme": false
  },
  "template": {
    "assignedSlug": "templates/pillar-property-loan.php",
    "relativePath": "templates/pillar-property-loan.php",
    "sizeBytes": 42811,
    "modifiedAt": 1788680000,
    "sha256": "...",
    "sharedTemplate": false,
    "assignedPageCount": 1,
    "readAllowed": true,
    "writeAllowed": true,
    "writeBlockReasons": []
  },
  "capabilities": {
    "phpLint": true,
    "atomicRename": true,
    "backup": true,
    "httpQa": true
  }
}
```

## 8. Theme read and dependency handling

`read` returns the full UTF-8 PHP source for one allowlisted/readable template plus hash, size, and modified timestamp.

The agent may inspect static calls such as `get_template_part()` and request additional individual files through the same safe read API when those files are within the active theme roots. v1 does not recursively rewrite dependencies automatically.

This keeps each write small, explicit, hash-guarded, and auditable.

## 9. Preview contract

The agent must preview before write.

Preview input:

```json
{
  "pageId": 123,
  "relativePath": "templates/pillar-property-loan.php",
  "expectedHash": "current-sha256",
  "replacementContent": "<?php ...",
  "qaNeedles": ["وام آزاد با سند ملکی"]
}
```

Bridge validates:

1. authenticated capability;
2. policy enabled;
3. path in active theme roots;
4. path allowlisted;
5. file not hard-denied;
6. current SHA-256 equals `expectedHash`;
7. replacement is UTF-8 text;
8. replacement size <= policy max;
9. PHP validation capability is available;
10. replacement PHP passes validation.

Preview returns:

- current hash;
- proposed hash;
- a bounded unified diff or line-change summary;
- file size delta;
- shared-template impact information;
- lint result;
- whether direct write is currently eligible;
- exact block reasons if not eligible;
- `zipFallbackRecommended=true` if direct write should not proceed.

Preview performs no production write.

## 10. PHP validation gate

Full-file production write is permitted only when Bridge can validate PHP syntax without executing the template.

Preferred implementation order:

1. a proven local PHP syntax-validation mechanism available on the host (for example a CLI lint process when execution functions are enabled); or
2. another compile-only mechanism that is covered by automated tests on the supported PHP runtime.

If no supported validator is available, `fullFileWriteEnabled` is effectively unavailable for that host and Bridge returns `php_lint_unavailable` plus `zipFallbackRecommended=true`.

The agent must never bypass this gate.

## 11. Concurrency and stale-write protection

Every read returns SHA-256 of the file bytes.

Every preview and write requires `expectedHash`.

Immediately before preview/write processing, Bridge recomputes the current hash. If it differs:

```text
409 theme_template_changed
```

No backup, temp replacement, or production write occurs.

This is the filesystem equivalent of the existing `expectedModified` guard for WordPress content.

## 12. Backup model

Before any production replacement, Bridge writes a backup record to a dedicated database table, not to a publicly reachable PHP backup file.

Suggested table: `${wpdb->prefix}digitalafarin_theme_backups`

Fields:

- `id` UUID/string primary key;
- `theme_stylesheet`;
- `relative_path`;
- `page_id` nullable;
- `operation_id`;
- `original_hash`;
- `replacement_hash`;
- `original_content` LONGTEXT;
- `created_by` WordPress user ID;
- `created_at`;
- `restored_at` nullable;
- `restore_operation_id` nullable.

The table is created/upgraded through a Bridge schema-version routine so upgrading an already-active plugin does not depend on a new activation event.

Retention is applied per file only after a successful write. The newest configured number of backups remains restorable.

## 13. Atomic production write

For a write that passed preview and current-hash revalidation:

1. recompute current hash and compare with `expectedHash`;
2. create the DB backup record;
3. create a temporary file in the same directory as the target;
4. write replacement bytes with an exclusive lock;
5. preserve appropriate file permissions;
6. run PHP validation against the temporary file;
7. compute the temp file hash and verify it equals the previewed proposed hash;
8. atomically rename the temp file over the target;
9. recompute the production file hash and verify it equals the expected replacement hash;
10. continue to HTTP QA.

If filesystem permissions do not permit same-directory temp creation and rename, no production write occurs and Bridge recommends ZIP fallback.

## 14. HTTP QA and automatic rollback

A theme update request is associated with the affected Page URL.

After the file is replaced, Bridge performs a same-site `wp_remote_get()` to the Page URL with a bounded timeout.

Required QA:

- HTTP status is 2xx;
- response body is non-empty.

Optional `qaNeedles` may be supplied during preview/write. Each needle is a bounded plain string that must be found in the HTML response. This lets the agent verify an expected H1, section marker, or critical CTA without executing arbitrary assertions.

If required QA fails and `autoRollbackOnQaFailure=true`:

1. restore the just-created backup through the same temp-file + validation + atomic rename path;
2. run a second HTTP request to confirm the previous version is serving;
3. return an error result with `rolledBack=true` and both QA outcomes.

The audit log must clearly distinguish `write_failed`, `qa_failed`, `auto_rollback_succeeded`, and `auto_rollback_failed`.

## 15. Manual restore

An administrator/agent can list backups for an allowlisted template and explicitly restore one backup.

Restore requirements:

- `manage_options`;
- active theme stylesheet must match backup theme stylesheet;
- target relative path must still resolve inside the active theme root;
- path must still be allowlisted;
- backup content must pass PHP validation before replacement;
- a new backup of the current version is created before restoring the older version, making restore itself reversible.

## 16. Bridge REST surface

Proposed v1 routes:

```text
GET  /digitalafarin/v1/theme/status
POST /digitalafarin/v1/theme/resolve-template
GET  /digitalafarin/v1/theme/file
POST /digitalafarin/v1/theme/file/preview
POST /digitalafarin/v1/theme/file/update
GET  /digitalafarin/v1/theme/backups
POST /digitalafarin/v1/theme/backups/{id}/restore
GET  /digitalafarin/v1/theme/policy
POST /digitalafarin/v1/theme/policy
```

`policy POST` exists for Dashboard administration but is not exposed as an SEO-agent MCP write tool.

## 17. MCP tool surface

Proposed agent-facing tools:

```text
wordpress_get_active_theme
wordpress_resolve_theme_template
wordpress_read_theme_template
wordpress_preview_theme_template_update
wordpress_update_theme_template
wordpress_list_theme_backups
wordpress_restore_theme_backup
```

No generic `wordpress_write_file`, `wordpress_execute_php`, or shell tool is introduced.

### Tool behavior

- `wordpress_get_active_theme`: read-only host/theme/write-safety capabilities.
- `wordpress_resolve_theme_template`: map Page ID or URL to actual theme template and policy state.
- `wordpress_read_theme_template`: read one resolved theme PHP file plus hash.
- `wordpress_preview_theme_template_update`: validate replacement and return diff/safety decision; no write.
- `wordpress_update_theme_template`: live operation; requires page/template/hash/proposed hash and replacement content that matches the preview.
- `wordpress_list_theme_backups`: read-only.
- `wordpress_restore_theme_backup`: destructive/live operation with explicit backup ID and current hash guard.

All live tools must have MCP descriptions and annotations that clearly state they modify production code.

## 18. Dashboard controls

Add a per-site "Theme Automation" panel under site/settings administration.

Admin controls:

- enable/disable Theme Automation;
- show active theme and detected capabilities;
- enable/disable full-file template writes;
- manage exact allowed files;
- manage allowed directories;
- configure max file size within a safe global ceiling;
- configure backup retention within a safe range;
- enable/disable automatic rollback on QA failure;
- display hard-denied files as immutable policy;
- test Bridge theme capability without changing files;
- list recent theme write/rollback audit entries.

Changing theme policy is an admin action and is audited.

The dashboard never displays backup source code by default. Source is only returned through explicit authenticated read/restore flows.

## 19. Audit events

At minimum, record:

```text
theme.policy_updated
theme.template_resolved
theme.template_read
theme.preview_created
theme.write_started
theme.write_succeeded
theme.write_blocked
theme.qa_failed
theme.auto_rollback_succeeded
theme.auto_rollback_failed
theme.backup_restored
```

Audit details may include site ID, Page ID, theme stylesheet/version, relative path, before/after hash, backup ID, diff counts, QA result, block reason, and operation ID. Do not store WordPress credentials in audit data.

## 20. SEO workflow after theme write

Theme template source and SEO metadata remain separate concerns.

For a pillar Page:

1. resolve and read template;
2. rewrite/preview/update template if needed;
3. verify HTTP QA;
4. use existing Page SEO tools for title/meta description/focus keyword/canonical/noindex;
5. use existing media tools where appropriate;
6. query GSC URL Inspection for indexed-state validation;
7. report changes and any manual Search Console Request Indexing recommendation.

No SEO metadata is hard-coded into the PHP template unless the theme itself intentionally owns that markup and the agent explicitly edits it as code.

## 21. ZIP fallback policy

Bridge returns `zipFallbackRecommended=true` and performs no direct write when any of these applies:

- template resolution is ambiguous;
- active theme cannot be safely resolved;
- target is outside the active theme roots;
- target is not allowlisted;
- target is hard-denied;
- target is a generic/shared template and policy does not explicitly allow it;
- current hash changed after read/preview;
- PHP syntax validation is unavailable;
- PHP validation fails;
- target directory is not safely writable for temp + atomic rename;
- replacement exceeds allowed size;
- source encoding/content cannot be handled safely;
- the agent determines the change spans multiple global theme files or architecture beyond the intended pillar template scope.

Fallback workflow:

```text
Current theme ZIP -> ChatGPT/source edit -> revised ZIP -> user deploys -> WordPress MCP SEO/meta/QA
```

This is a first-class supported workflow, not an error workaround.

## 22. Source-of-truth and deployment drift

A direct production template edit can diverge from the developer's local/Git/theme-ZIP source. v1 records before/after hashes and diffs but does not automatically push the patch to Git.

Therefore:

- dashboard/audit must make direct production template writes visible;
- a later theme deployment can overwrite direct edits;
- substantial architectural changes should prefer the ZIP/Git source workflow;
- future Git integration may synchronize approved production patches back into the source repository, but that is outside v1.

This limitation is acceptable for the DigitalAfarin-owned custom sites because theme updates are controlled, but it must remain visible in the product.

## 23. Error model

Use stable codes so the Agent can choose fallback instead of improvising:

```text
theme_automation_disabled
theme_not_resolved
template_not_found
template_outside_theme_root
template_not_allowlisted
template_hard_denied
template_shared_write_blocked
theme_template_changed
replacement_too_large
replacement_invalid_utf8
php_lint_unavailable
php_lint_failed
filesystem_not_writable
backup_failed
atomic_replace_failed
post_write_hash_mismatch
http_qa_failed
auto_rollback_failed
backup_not_found
backup_theme_mismatch
```

Errors that mean direct production writing should stop include `zipFallbackRecommended: true`.

## 24. Testing strategy

Implementation must use TDD.

### Bridge/PHP tests

Cover at minimum:

- active theme status;
- custom page-template resolution;
- page-specific hierarchy resolution;
- generic/shared template detection;
- traversal rejection;
- symlink escape rejection;
- hard-deny enforcement;
- allowlist enforcement;
- stale hash rejection;
- replacement size validation;
- lint unavailable -> write blocked/fallback;
- lint failure -> no production change;
- successful temp-file atomic replacement;
- backup created before write;
- failed QA -> automatic rollback;
- restore creates a backup of the version being replaced;
- backup retention;
- capability enforcement;
- policy updates require administrator capability.

### MCP/TypeScript tests

Cover:

- correct Bridge routes/parameters;
- safe serialization of template source;
- required `expectedHash` on preview/write;
- proposed hash returned by preview must match write payload;
- Bridge error codes surface without being hidden;
- live tool annotations accurately indicate production mutation;
- no tool exists to modify the allowlist/policy.

### Dashboard tests

Cover:

- theme automation defaults disabled;
- policy form validation;
- exact allowed file/directory normalization;
- hard-denied files cannot be configured;
- capability test is read-only;
- admin audit entries are rendered.

### Deployment verification

On a test/staging WordPress site with a custom pillar template:

1. resolve template;
2. read and record hash;
3. preview a harmless visible text change;
4. verify production file is unchanged after preview;
5. write the change;
6. verify HTTP 200 and needle;
7. verify backup exists;
8. restore backup;
9. verify original hash and original page output;
10. deliberately submit stale hash and confirm 409/no write;
11. deliberately submit invalid PHP and confirm no write.

## 25. Rollout

1. Ship Agent Bridge schema/policy/status/read/discovery first with writes disabled.
2. Deploy MCP read/discovery/preview tools and validate against one DigitalAfarin site.
3. Enable full-file write policy only on one test site/template.
4. Execute write + QA + restore acceptance test.
5. Enable selected pillar templates on additional owned sites.
6. Keep all other sites in read-only/ZIP-fallback mode until explicitly configured.

## 26. Acceptance criteria

The feature is complete when:

- the agent can take a pillar Page URL and identify its actual active-theme PHP template without guessing;
- the agent can read that template source;
- the agent cannot write files outside explicitly allowed theme locations;
- hard-denied global files remain non-writable;
- full-file writes are impossible without syntax validation;
- every write is hash-guarded and backed up;
- production replacement is atomic or refused;
- failed HTTP QA triggers configured automatic rollback;
- backups can be listed and restored safely;
- Dashboard controls the site policy and the SEO agent cannot expand its own permissions;
- Page SEO metadata continues through the existing Page SEO tools;
- unsafe/unsupported hosts receive a clear ZIP fallback recommendation rather than a risky write attempt.
