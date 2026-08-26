# DigitalAfarin WordPress MCP

نسخه آزمایشی و کم‌دسترسی برای اتصال ChatGPT/Codex به WordPress REST API.

## محدوده امنیتی نسخه 0.1

- ابزار حذف، انتشار، نصب افزونه یا تغییر تنظیمات ندارد.
- `wordpress_create_draft` همیشه `status=draft` ارسال می‌کند.
- `wordpress_update_draft` ابتدا وضعیت را از وردپرس می‌خواند و اگر Draft نباشد درخواست را رد می‌کند.
- رمز وردپرس فقط از Environment خوانده می‌شود و در پاسخ یا لاگ ثبت نمی‌شود.
- سرویس پیش‌فرض فقط روی `127.0.0.1` گوش می‌دهد.

## ابزارها

1. `wordpress_health_check`
2. `wordpress_search_posts`
3. `wordpress_get_post`
4. `wordpress_list_categories`
5. `wordpress_create_draft`
6. `wordpress_update_draft`

## اجرای محلی

نیازمندی: Node.js 20 یا بالاتر.

```bash
cp .env.example .env
npm install
npm run build
npm start
```

رمز جدید Application Password را در `.env` قرار دهید. فایل `.env` نباید commit یا ارسال شود.

تست سلامت سرویس:

```bash
curl http://127.0.0.1:3030/health
```

تست MCP Inspector:

```bash
npx @modelcontextprotocol/inspector@latest
```

در Inspector، Transport را روی `Streamable HTTP` و URL را روی زیر بگذارید:

```text
http://127.0.0.1:3030/mcp
```

اگر `MCP_BEARER_TOKEN` تنظیم شده، هدر `Authorization: Bearer TOKEN` را نیز در Inspector وارد کنید.

## استقرار روی VPS

```bash
sudo mkdir -p /var/www/digitalafarin-wordpress-mcp
sudo chown deploy:deploy /var/www/digitalafarin-wordpress-mcp
```

فایل‌های پروژه را در مسیر بالا قرار دهید، سپس:

```bash
cd /var/www/digitalafarin-wordpress-mcp
npm ci
npm run build
sudo cp deploy/digitalafarin-wordpress-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digitalafarin-wordpress-mcp
sudo systemctl status digitalafarin-wordpress-mcp --no-pager
```

برای نصب کنترل‌شده روی سرور، پس از قرار دادن پروژه در مسیر فوق اجرا کنید:

```bash
sudo bash /var/www/digitalafarin-wordpress-mcp/deploy/install-server.sh
```

اجرای اول در صورت نبود Environment، فایل امن `/etc/digitalafarin-wordpress-mcp.env` را با placeholder می‌سازد و متوقف می‌شود. رمز واقعی را داخل همان فایل وارد و اسکریپت را دوباره اجرا کنید.

### GitHub Actions

Workflow دستی `.github/workflows/deploy.yml` اضافه شده است. Secrets محیط `production`:

```text
SSH_HOST=<server hostname or IP>
SSH_PORT=<SSH port, usually 22>
SSH_USER=<restricted deployment user>
SSH_PRIVATE_KEY=<matching private deployment key>
```

کاربر استقرار باید فقط اجازه اجرای اسکریپت بروزرسانی همین پروژه را بدون رمز داشته باشد. مسیر دقیق را با محل نصب واقعی پروژه جایگزین کنید:

```text
DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/bash APP_DIR/deploy/update-server.sh
```

فایل محرمانه زیر را با دسترسی root بسازید:

```text
/etc/digitalafarin-wordpress-mcp.env
```

نمونه محتوا:

```env
WP_BASE_URL=https://vamfori24.com
WP_USERNAME=digitalafarin_agent
WP_APP_PASSWORD=NEW_APPLICATION_PASSWORD
PORT=3030
HOST=127.0.0.1
ALLOWED_ORIGINS=https://chatgpt.com
MAX_POST_CONTENT_BYTES=500000
```

و دسترسی آن را محدود کنید:

```bash
sudo chown root:root /etc/digitalafarin-wordpress-mcp.env
sudo chmod 600 /etc/digitalafarin-wordpress-mcp.env
```

پس از تغییر Environment:

```bash
sudo systemctl restart digitalafarin-wordpress-mcp
```

## اتصال امن به ChatGPT

چون این MCP به داده خصوصی دسترسی دارد و Draft ایجاد می‌کند، آن را بدون احراز هویت روی اینترنت عمومی باز نکنید. برای تست خصوصی، سرویس را روی localhost نگه دارید و از **Secure MCP Tunnel** در Developer Mode استفاده کنید. در پنجره اتصال Plugin، Connection را روی Tunnel بگذارید و Tunnel ID ایجادشده را انتخاب کنید.

برای انتشار عمومی یا استفاده چندکاربره، باید OAuth مطابق MCP Authorization پیاده‌سازی شود؛ Bearer Token ثابت جایگزین OAuth عمومی نیست.

## تست پیشنهادی در ChatGPT

1. «اتصال وردپرس را بررسی کن.»
2. «۱۰ نوشته‌ای که اخیراً تغییر کرده‌اند را نشان بده.»
3. «دسته‌های مربوط به وام را پیدا کن.»
4. «یک مقاله آزمایشی با وضعیت Draft بساز.»
5. تلاش کنید یک نوشته Published را با `wordpress_update_draft` تغییر دهید؛ سرور باید آن را رد کند.

## نکات Yoast SEO

REST API اصلی وردپرس مدیریت مقاله، دسته و محتوا را پوشش می‌دهد. فیلدهای خصوصی Yoast لزوماً برای نوشتن از REST API عمومی ثبت نشده‌اند. اتصال Yoast در نسخه بعدی با یک افزونه کوچک WordPress و endpoint محدود انجام می‌شود؛ در نسخه 0.1 هیچ متای Yoast تغییر نمی‌کند.
