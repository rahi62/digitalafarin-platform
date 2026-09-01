# DigitalAfarin WordPress + Search Console MCP

MCP چندسایته برای اتصال ChatGPT به WordPress و Google Search Console و اجرای workflow کنترل‌شده سئو و مدیریت محتوا.

## معماری

```text
                         ┌─ WordPress REST API
ChatGPT / Agent → MCP → Dashboard localhost brokers
                         └─ Google Search Console API
                                  ↑
                    encrypted PostgreSQL control plane
```

Dashboard محل مدیریت سایت‌ها، credentialها، Integrationها و ابزارهای حساس ادمین است. Secretهای محصول داخل source code یا پاسخ Agent قرار نمی‌گیرند.

## مدل Product-ready

Environment فقط برای secretهای زیرساختی باقی می‌ماند:

```env
DATABASE_URL=...
ADMIN_PASSWORD_SHA256=...
SESSION_SECRET=...
CREDENTIALS_ENCRYPTION_KEY=...
```

Google OAuth Client ID/Secret و سایر Integrationهای محصول از پنل تنظیم می‌شوند و در PostgreSQL ذخیره می‌شوند. Client Secret و Refresh Token با AES-256-GCM رمزنگاری می‌شوند.

- **Hosted SaaS**: DigitalAfarin OAuth App مرکزی را مدیریت می‌کند و مشتری فقط Google Account خود را Connect می‌کند.
- **White-label / Self-hosted**: مدیر هر نصب OAuth Client اختصاصی خودش را از پنل ثبت می‌کند.

Phase فعلی هنوز single-admin است. milestone بعدی برای SaaS چندمشتری: Workspace/Tenant، User/Role، جداسازی credentialها و Billing.

## مدل امنیتی نسخه 0.6

- مقاله جدید ابتدا Draft ساخته می‌شود و انتشار ابزار مستقل دارد.
- تغییر Published به‌صورت Live و فقط با ابزار جدا انجام می‌شود.
- `expectedModified` برای جلوگیری از overwrite نسخه جدیدتر پشتیبانی می‌شود.
- Upload تصویر از URL فقط HTTPS است و مقصد private/reserved network رد می‌شود.
- Search Console فقط read-only است.
- **Noindex** فقط روی Draft/Published و از Bridge کنترل‌شده اعمال می‌شود.
- **301 Redirect** فقط از Bridge و با capability سطح ادمین `manage_options` قابل مدیریت است.
- **Delete عادی** فقط Post را به WordPress Trash می‌برد.
- **Permanent Delete** فقط وقتی Post از قبل Trash باشد و عبارت تأیید دقیق `PERMANENTLY DELETE POST <id>` ارسال شود انجام می‌شود.
- ابزار Permanent Delete به‌عنوان destructive در MCP علامت‌گذاری شده است.
- هیچ ابزار نصب افزونه، تغییر Theme یا اجرای کد arbitrary در WordPress وجود ندارد.

## ابزارهای MCP

### WordPress Read

- `wordpress_list_sites`
- `wordpress_health_check`
- `wordpress_search_posts`
- `wordpress_get_post`
- `wordpress_list_categories`
- `wordpress_list_tags`
- `wordpress_list_media`
- `wordpress_get_seo`
- `wordpress_admin_capabilities`
- `wordpress_get_indexing`
- `wordpress_list_redirects`

### WordPress Content Write

- `wordpress_create_draft`
- `wordpress_update_draft`
- `wordpress_publish_draft`
- `wordpress_update_published_post`
- `wordpress_create_tag`
- `wordpress_upload_media_from_url`
- `wordpress_upload_media_base64`
- `wordpress_update_media_metadata`
- `wordpress_set_featured_image`
- `wordpress_update_draft_seo`
- `wordpress_update_post_seo`

### WordPress Admin / SEO

- `wordpress_set_noindex`
  - `noindex=true` اعمال Noindex
  - `noindex=false` حذف override
- `wordpress_create_301_redirect`
  - Source باید مسیر نسبی مثل `/old-page` باشد.
  - Target می‌تواند مسیر نسبی یا URL HTTP(S) باشد.
  - Redirect به‌صورت exact path و با status 301 اجرا می‌شود.
- `wordpress_delete_redirect`
- `wordpress_trash_post`
- `wordpress_delete_post_permanently`
  - فقط Post از قبل Trash شده
  - confirmation دقیق الزامی است

Redirectها نیازمند `manage_options` هستند. بنابراین WordPress API user برای این عملیات باید Administrator باشد یا capability معادل داشته باشد. Noindex و Delete از capabilityهای native همان Post استفاده می‌کنند.

## Google Search Console

- `gsc_list_sites`
- `gsc_search_analytics`
  - Clicks، Impressions، CTR و Average Position
  - dimensions: `query`, `page`, `country`, `device`, `searchAppearance`, `date`, `hour`
  - filters و pagination
- `gsc_inspect_url`
- `gsc_list_sitemaps`

تمام ابزارهای GSC فقط Read-only هستند.

## DigitalAfarin Agent Bridge

فایل افزونه:

```text
wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php
```

Bridge 0.3 این قابلیت‌ها را فراهم می‌کند:

- SEO title / Meta description / Focus keyword / Canonical برای Yoast و Rank Math
- Noindex override مستقل و سازگار با robots output
- 301 Redirect مستقل از Yoast Premium یا Rank Math Pro

سطح دسترسی:

- SEO / Noindex: کاربر authenticated دارای `edit_post`
- Redirect: کاربر دارای `manage_options`

Bridge امکان اجرای arbitrary PHP، نصب افزونه یا تغییر Theme را نمی‌دهد.

## Environment MCP

```env
SITE_BROKER_URL=http://127.0.0.1:3040/api/internal/sites
GSC_BROKER_URL=http://127.0.0.1:3040/api/internal/gsc
PORT=3030
HOST=127.0.0.1
ALLOWED_ORIGINS=https://chatgpt.com
MCP_BEARER_TOKEN=
MAX_POST_CONTENT_BYTES=500000
MAX_MEDIA_BYTES=10000000
```

## راه‌اندازی Google Search Console

1. Google Search Console API را در Google Cloud Enable کنید.
2. OAuth consent screen را تنظیم کنید.
3. OAuth Client از نوع Web application بسازید.
4. در Dashboard → تنظیمات و اتصال‌ها، Client ID/Secret را ثبت کنید.
5. Callback URL پنل را در Google Cloud ثبت کنید.
6. حساب Google را Connect کنید.
7. Property هر سایت را map کنید.

## Build و Deploy

```bash
npm ci
npm run check
npm run build

cd /var/www/digitalafarin-wordpress-mcp
sudo -u deploy git pull --ff-only origin main
sudo bash deploy/update-server.sh
curl -s http://127.0.0.1:3030/health
```

Health نسخه جدید باید `0.6.0` را برگرداند.

## Workflow حذف پیشنهادی

1. Post را با `wordpress_get_post` بخوان و ID/عنوان/modified را تأیید کن.
2. با درخواست صریح کاربر `wordpress_trash_post` را اجرا کن.
3. در صورت نیاز امکان بازیابی از WordPress Admin باقی می‌ماند.
4. فقط اگر کاربر صراحتاً حذف غیرقابل‌بازگشت خواست، Post باید از قبل Trash باشد.
5. سپس `wordpress_delete_post_permanently` با confirmation دقیق اجرا شود.

این سیاست عمداً از حذف دائمی تک‌مرحله‌ای جلوگیری می‌کند.
