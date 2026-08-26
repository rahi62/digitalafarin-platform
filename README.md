# DigitalAfarin WordPress + Search Console MCP

MCP چندسایته برای اتصال ChatGPT به WordPress و Google Search Console و اجرای workflow کنترل‌شده سئو.

## معماری

```text
                         ┌─ WordPress REST API
ChatGPT / Agent → MCP → Dashboard localhost brokers
                         └─ Google Search Console API
                                  ↑
                       encrypted PostgreSQL registry
```

Dashboard محل مدیریت اتصال‌هاست. Credentialهای WordPress و Google Refresh Token در پاسخ Agent نمایش داده نمی‌شوند. MCP فقط credential کوتاه‌عمر/لازم برای هر عملیات را از brokerهای loopback دریافت می‌کند.

## مدل امنیتی نسخه 0.5

- ابزار حذف محتوا وجود ندارد.
- مقاله جدید ابتدا با `wordpress_create_draft` ساخته می‌شود.
- انتشار فقط از ابزار مستقل `wordpress_publish_draft` انجام می‌شود.
- `wordpress_update_draft` فقط Draft را تغییر می‌دهد.
- `wordpress_update_published_post` فقط Published را تغییر می‌دهد و نوشته را Published نگه می‌دارد.
- تغییرات Live باید فقط در پاسخ به درخواست صریح کاربر اجرا شوند.
- Featured Image و SEO برای Draft و Published پشتیبانی می‌شوند.
- `expectedModified` می‌تواند از overwrite شدن تغییرات جدیدتر جلوگیری کند.
- Upload تصویر از URL فقط HTTPS است و مقصد private/reserved network رد می‌شود.
- WordPress Application Password و Google Refresh Token با AES-256-GCM در Dashboard رمزنگاری می‌شوند.
- Search Console با scope فقط‌خواندنی `https://www.googleapis.com/auth/webmasters.readonly` متصل می‌شود.
- Google Client Secret و Refresh Token هرگز به MCP/ChatGPT برگردانده نمی‌شوند؛ broker فقط Access Token کوتاه‌عمر می‌دهد.
- brokerهای `/api/internal/sites` و `/api/internal/gsc` فقط روی loopback + internal header کار می‌کنند و باید در Nginx به‌صورت عمومی block باشند.

## ابزارهای MCP نسخه 0.5

### WordPress

Read:
- `wordpress_list_sites`
- `wordpress_health_check`
- `wordpress_search_posts`
- `wordpress_get_post`
- `wordpress_list_categories`
- `wordpress_list_tags`
- `wordpress_list_media`
- `wordpress_get_seo`

Write:
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

Create + Publish عمداً دو مرحله‌ای است تا مقاله، تصاویر و SEO قبل از زنده شدن کامل شوند.

### Google Search Console

- `gsc_list_sites`
  - سایت‌های enabled که در Dashboard به GSC Property نگاشت شده‌اند.
- `gsc_search_analytics`
  - دریافت Clicks، Impressions، CTR و Average Position.
  - dimensions: `query`, `page`, `country`, `device`, `searchAppearance`, `date`, `hour`
  - filters: query/page/country/device/searchAppearance
  - search type: web/image/video/news/discover/googleNews
  - rowLimit تا 25000 و startRow برای pagination.
- `gsc_inspect_url`
  - وضعیت نسخه موجود یک URL در Google Index، canonical/indexing/crawl-related inspection data در صورت موجود بودن.
  - این API Live URL Test اجرا نمی‌کند.
- `gsc_list_sitemaps`
  - مشاهده Sitemapهای ثبت‌شده برای Property و در صورت نیاز فیلتر بر اساس sitemap index.

تمام ابزارهای GSC فقط Read-only هستند و هیچ تغییر Search Console از MCP انجام نمی‌شود. Search Analytics در queryهای بزرگ top rows را برمی‌گرداند و تضمین نمی‌کند تمام ترکیب‌های ممکن dimension در یک پاسخ وجود داشته باشند.

## DigitalAfarin Agent Bridge

برای SEO write روی WordPress افزونه زیر باید نصب و فعال باشد:

```text
wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php
```

Bridge 0.2 برای کاربر authenticated دارای `edit_post`، SEO نوشته‌های `draft` و `publish` را برای Yoast SEO و Rank Math مدیریت می‌کند:

- SEO title
- Meta description
- Focus keyword
- Canonical URL

Bridge امکان Delete، نصب افزونه یا تغییر تنظیمات عمومی WordPress را ندارد.

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

فایل production:

```text
/etc/digitalafarin-wordpress-mcp.env
```

## Environment Dashboard

```env
DATABASE_URL=...
ADMIN_PASSWORD_SHA256=...
SESSION_SECRET=...
CREDENTIALS_ENCRYPTION_KEY=...
GSC_GOOGLE_CLIENT_ID=...
GSC_GOOGLE_CLIENT_SECRET=...
GSC_GOOGLE_REDIRECT_URI=https://wp-agent.digitalafarin.ir/api/gsc/oauth/callback
```

فایل production:

```text
/etc/digitalafarin-wp-agent.env
```

این فایل باید root-owned و mode `600` باشد. Secretها را commit نکنید.

## راه‌اندازی Google Search Console OAuth

1. در Google Cloud یک Project انتخاب/ایجاد کنید.
2. Google Search Console API را برای Project فعال کنید.
3. OAuth consent screen را تنظیم کنید.
4. OAuth Client با نوع **Web application** بسازید.
5. Authorized redirect URI را دقیقاً برابر Dashboard callback قرار دهید:

```text
https://wp-agent.digitalafarin.ir/api/gsc/oauth/callback
```

6. Client ID و Client Secret را فقط داخل `/etc/digitalafarin-wp-agent.env` قرار دهید.
7. deploy را اجرا کنید.
8. در Dashboard وارد **تنظیمات و اتصال‌ها** شوید و **اتصال حساب Google** را بزنید.
9. بعد از OAuth، برای هر WordPress Site یک Search Console Property انتخاب کنید. Property می‌تواند URL-prefix یا domain property مثل `sc-domain:example.com` باشد.
10. Connector/MCP را refresh کنید و `gsc_list_sites`، `gsc_search_analytics`، `gsc_inspect_url` و `gsc_list_sitemaps` را تست کنید.

اگر OAuth consent screen در حالت Testing باشد، Google Account مورد استفاده باید در Test users قرار داشته باشد.

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

Health نسخه 0.5 باید `version: "0.5.0"` برگرداند.

## Workflow هدف سئو

### مقاله جدید

1. داده‌های GSC را برای Query/Page/CTR/Position تحلیل کن.
2. Keyword/Intent و gap محتوایی را مشخص کن.
3. Category/Tag را انتخاب کن.
4. Draft جدید بساز.
5. محتوا و تصاویر را تولید و Upload کن؛ alt/title/caption و Featured Image را تنظیم کن.
6. SEO meta را از Bridge تنظیم کن.
7. Draft را بازخوانی و کنترل کن.
8. در صورت درخواست صریح کاربر، Publish کن.
9. URL نهایی و تغییرات را گزارش کن.

### آپدیت مقاله موجود

1. GSC Query/Page performance و در صورت نیاز URL Inspection/Sitemap را بخوان.
2. مقاله Published و `modified` فعلی را بخوان.
3. مشکل CTR، intent mismatch، content decay، indexing issue یا فرصت position را تحلیل کن.
4. محتوا/Media/SEO را با guard مناسب به‌روزرسانی کن.
5. دوباره WordPress و در صورت نیاز GSC را بخوان و گزارش تغییرات بده.

## سیاست حذف

Delete عمداً در نسخه 0.5 وجود ندارد. برای workflow تولید و بهینه‌سازی سئو ضروری نیست و اگر بعداً اضافه شود باید ابزار جدا با تأیید قوی داشته باشد.
