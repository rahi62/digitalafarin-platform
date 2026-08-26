# DigitalAfarin WordPress MCP

MCP چندسایته برای اتصال ChatGPT به WordPress و مدیریت کنترل‌شده محتوای سئو.

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

## مدل امنیتی نسخه 0.4

- ابزار حذف محتوا وجود ندارد.
- مقاله جدید ابتدا با `wordpress_create_draft` ساخته می‌شود.
- انتشار فقط از ابزار مستقل `wordpress_publish_draft` و فقط وقتی status فعلی `draft` باشد انجام می‌شود.
- `wordpress_update_draft` فقط Draft را تغییر می‌دهد.
- `wordpress_update_published_post` فقط Published را تغییر می‌دهد و status را `publish` نگه می‌دارد.
- ابزارهای Live در description صراحتاً مشخص شده‌اند و باید فقط با درخواست کاربر استفاده شوند.
- Featured Image برای Draft و Published قابل تنظیم است.
- SEO برای Draft و Published از Bridge محدود DigitalAfarin قابل مدیریت است.
- `expectedModified` اختیاری برای Publish/Live Update/SEO/Featured Image از overwrite کردن نسخه‌ای که بعد از تحلیل تغییر کرده جلوگیری می‌کند.
- Upload از URL فقط HTTPS است و مقصدهای private/reserved network رد می‌شوند.
- حجم محتوا و تصویر محدود است.
- سرویس MCP و credential broker روی loopback اجرا می‌شوند.
- Application Passwordها در Dashboard با AES-256-GCM رمزنگاری می‌شوند.

## ابزارهای MCP نسخه 0.4

### Sites / Read

- `wordpress_list_sites`
- `wordpress_health_check`
- `wordpress_search_posts`
- `wordpress_get_post`
- `wordpress_list_categories`

### Content Write

- `wordpress_create_draft`
- `wordpress_update_draft`
- `wordpress_publish_draft`
- `wordpress_update_published_post`

Create + Publish عمداً دو مرحله‌ای است. Agent می‌تواند یک مقاله جدید را Draft بسازد، تصاویر/SEO/Taxonomy را کامل کند و سپس در صورت درخواست صریح کاربر آن را Publish کند.

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
- `wordpress_update_post_seo`

برای نوشتن SEO باید افزونه زیر روی سایت نصب و فعال باشد:

```text
wordpress-plugin/digitalafarin-agent-bridge/digitalafarin-agent-bridge.php
```

Bridge نسخه 0.2 فقط برای کاربر authenticated دارای `edit_post` کار می‌کند و SEO Postهای `draft` و `publish` را پشتیبانی می‌کند. Providerهای پشتیبانی‌شده:

- Rank Math
- Yoast SEO

فیلدهای قابل مدیریت:

- SEO title
- Meta description
- Focus keyword
- Canonical URL

Bridge امکان Delete، نصب افزونه یا تغییر تنظیمات عمومی WordPress را اضافه نمی‌کند.

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

Credentialهای WordPress در Environment MCP قرار نمی‌گیرند و از Site Registry پنل resolve می‌شوند.

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

```bash
cd /var/www/digitalafarin-wordpress-mcp
sudo -u deploy git pull --ff-only origin main
sudo bash deploy/update-server.sh
```

فایل Environment سرویس:

```text
/etc/digitalafarin-wordpress-mcp.env
```

باید متعلق به root و mode آن `600` باشد.

## Workflow هدف

### مقاله جدید

1. تحلیل Keyword/Intent و محتوای رقبا/داده‌های Search Console.
2. انتخاب Category و Tag.
3. ساخت مقاله با `wordpress_create_draft`.
4. تولید و Upload تصاویر و تنظیم alt/title/caption.
5. درج تصاویر داخل HTML و تنظیم Featured Image.
6. تنظیم SEO title/meta/focus keyword/canonical.
7. بازخوانی Draft نهایی.
8. در صورت درخواست صریح کاربر: `wordpress_publish_draft`.
9. بازخوانی Published post و گزارش URL نهایی.

### آپدیت مقاله موجود

1. خواندن مقاله Published و ثبت `modified`.
2. تحلیل SEO و طراحی تغییرات.
3. اعمال محتوا با `wordpress_update_published_post` و در صورت نیاز `expectedModified`.
4. اعمال Media/Featured Image/SEO در صورت درخواست.
5. بازخوانی مقاله زنده و گزارش دقیق تغییرات.

## سیاست حذف

Delete عمداً در نسخه 0.4 وجود ندارد. حذف محتوا برای workflow تولید و بهینه‌سازی سئو ضروری نیست و در صورت نیاز باید به شکل ابزار جدا با سیاست تأیید قوی طراحی شود.
