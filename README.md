# DigitalAfarin WordPress MCP

MCP امن و چندسایته برای اتصال ChatGPT به WordPress و مدیریت کنترل‌شده محتوا.

## معماری

```text
ChatGPT / Agent
      ↓
DigitalAfarin WordPress MCP
      ↓
Dashboard credential broker (localhost only)
      ↓
Encrypted PostgreSQL site registry
      ↓
WordPress REST API
```

Credential وردپرس داخل ابزار یا پاسخ Agent نمایش داده نمی‌شود. سایت‌ها از Dashboard فعال/غیرفعال می‌شوند و MCP فقط سایت‌های enabled را resolve می‌کند.

## مدل امنیتی

- هیچ ابزار حذف محتوا ندارد.
- `wordpress_create_draft` همیشه Draft می‌سازد.
- `wordpress_update_draft` فقط Draft را تغییر می‌دهد و Published/Pending/Private/Scheduled را رد می‌کند.
- تغییر Featured Image فقط برای Draft مجاز است.
- تغییر SEO فقط برای Draft و فقط از Bridge محدود DigitalAfarin انجام می‌شود.
- Upload از URL فقط HTTPS است و مقصدهای private/reserved network رد می‌شوند.
- حجم محتوا و تصویر محدود است.
- سرویس MCP و credential broker روی loopback اجرا می‌شوند.
- Application Passwordها در Dashboard با AES-256-GCM رمزنگاری می‌شوند.

## ابزارهای MCP نسخه 0.3

### Sites / Content

- `wordpress_list_sites`
- `wordpress_health_check`
- `wordpress_search_posts`
- `wordpress_get_post`
- `wordpress_list_categories`
- `wordpress_create_draft`
- `wordpress_update_draft`

### Tags

- `wordpress_list_tags`
- `wordpress_create_tag`

### Media

- `wordpress_list_media`
- `wordpress_upload_media_from_url`
- `wordpress_upload_media_base64`
- `wordpress_update_media_metadata`
- `wordpress_set_featured_image`

`wordpress_upload_media_base64` برای تصاویر تولیدشده یا فایل‌هایی است که Agent بتواند به bytes/base64 تبدیل کند. فرمت‌های مجاز: JPEG, PNG, WebP و GIF.

### SEO

- `wordpress_get_seo`
- `wordpress_update_draft_seo`

خواندن SEO تا حدی از REST pluginهای شناخته‌شده انجام می‌شود. برای نوشتن SEO باید افزونه زیر روی سایت نصب باشد:

```text
wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php
```

Bridge فقط برای کاربر authenticated که مجوز `edit_post` دارد کار می‌کند و فقط SEO یک Post با وضعیت Draft را تغییر می‌دهد. Providerهای پشتیبانی‌شده:

- Rank Math
- Yoast SEO

فیلدهای قابل مدیریت:

- SEO title
- Meta description
- Focus keyword
- Canonical URL

Bridge امکان Publish، Delete، نصب افزونه یا تغییر تنظیمات عمومی WordPress را اضافه نمی‌کند.

## Environment

```env
SITE_BROKER_URL=http://127.0.0.1:3040/api/internal/sites
PORT=3030
HOST=127.0.0.1
ALLOWED_ORIGINS=https://chatgpt.com
MCP_BEARER_TOKEN=
MAX_POST_CONTENT_BYTES=500000
MAX_MEDIA_BYTES=10000000
```

Credentialهای WordPress دیگر در Environment MCP قرار نمی‌گیرند و از Site Registry پنل resolve می‌شوند.

## Build

نیازمندی: Node.js 20 یا بالاتر.

```bash
npm ci
npm run check
npm run build
```

تست سلامت:

```bash
curl http://127.0.0.1:3030/health
```

## Deploy روی VPS

در نصب فعلی:

```bash
cd /var/www/digitalafarin-wordpress-mcp
sudo -u deploy git pull --ff-only origin main
sudo bash deploy/update-server.sh
```

برای نصب اولیه:

```bash
sudo bash deploy/install-server.sh
```

فایل Environment سرویس:

```text
/etc/digitalafarin-wordpress-mcp.env
```

باید متعلق به root و mode آن `600` باشد.

## DigitalAfarin Agent Bridge

برای SEO write فایل PHP افزونه را به شکل یک Plugin وردپرس بسته‌بندی/نصب و فعال کنید. نصب این Bridge یک عملیات Administrator است و عمداً از MCP با نقش Editor انجام نمی‌شود.

پس از فعال‌سازی، این تست باید authenticated و موفق باشد:

```text
GET /wp-json/digitalafarin/v1/posts/<DRAFT_ID>/seo
```

و MCP می‌تواند `wordpress_update_draft_seo` را روی همان Draft اجرا کند.

## Workflow هدف

Workflow نهایی از داخل ChatGPT می‌تواند به این شکل باشد:

1. تحلیل محتوای موجود و داده‌های SEO/Search Console.
2. انتخاب یا پیشنهاد Keyword و ساختار مقاله.
3. جستجو/ساخت Tag و Category مناسب.
4. تولید مقاله به صورت Draft.
5. آماده‌سازی و Upload تصاویر با alt/title/caption مناسب.
6. درج URL تصاویر داخل HTML Draft.
7. تنظیم Featured Image.
8. تنظیم SEO title/meta/focus keyword از Bridge.
9. بازخوانی نهایی Draft و ارائه گزارش تغییرات برای تأیید انسانی.

Publish همچنان خارج از این workflow امن است مگر در نسخه آینده با سیاست تأیید صریح جداگانه طراحی شود.
