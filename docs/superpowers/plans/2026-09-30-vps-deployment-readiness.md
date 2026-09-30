# VPS Deployment Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This document is an audit and proposed roadmap; implementation has not started.

**Goal:** تکمیل مدیریت دیپلوی پروژه‌های خود کاربر روی VPS، از اتصال repository تا اجرای سالم، بروزرسانی، rollback و بازیابی داده.

**Architecture:** حفظ Django Control Plane، Host Agent خروجی‌محور، Next.js و systemd. عملیات طولانی asynchronous و typed باقی می‌مانند؛ helper محدود مسئول تغییرات privileged است و build/runtime با کاربر غیر root اجرا می‌شوند. وضعیت پنل باید از نتیجهٔ واقعی host و health به دست آید.

**Tech Stack:** Django/DRF، PostgreSQL برای Control Plane در production، Python Agent، Next.js، systemd، Nginx، Certbot، Git.

**Spec:** درخواست فارسی کاربر در 2026-09-30 و متن پیوست دربارهٔ one-click provisioning؛ درخواست فعلی خروجی ممیزی و پلن است. توسعهٔ MCP و Telegram خارج از محدوده است.

## محدوده و تصمیم پیشنهادی

فرض این برآورد: محصول برای پروژه‌های خود کاربر و VPSهای تحت مدیریت اوست؛ ابتدا Ubuntu 24.04، Next.js، Django و PostgreSQL. ارائهٔ عمومی سرویس به مشتریان ناشناس، billing، Kubernetes، autoscaling، HA، preview deployment و تضمین zero-downtime در این برآورد نیست. staging/production و workerهای عمومی می‌توانند پس از مسیر اصلی اضافه شوند؛ UI نباید پیش از پیاده‌سازی، پشتیبانی آن‌ها را القا کند.

سه مسیر قابل انتخاب‌اند: تکمیل systemd موجود، افزودن executor مبتنی بر container، یا تعویض هستهٔ مدیریت deployment. پیشنهاد این ممیزی تکمیل systemd است چون release، takeover و مرز helper قبلاً ساخته شده‌اند. container گزینهٔ توسعهٔ بعدی است و اضافه‌کردنش اکنون دامنهٔ تست، storage و networking را زیاد می‌کند. تعویض هسته نیز ارزش بخش بزرگی از کد فعلی را از بین می‌برد.

## Global Constraints

- هیچ push، rollout، restart یا تغییر روی VPS در این مرحله انجام نشده است.
- فایل‌های کاربر، hotfixها، adopted/configured/managed و controlled takeover باید حفظ شوند.
- API، Agent و helper نباید command array، shell، unit دلخواه یا مسیر اجرایی مطلق از caller بپذیرند.
- identity، unit، مسیر release، کاربر اجرا و EnvironmentFile باید از metadata معتبر و policy داخلی مشتق شوند.
- وضعیت managed فقط بعد از موفقیت واقعی provisioning و health ثبت شود؛ managed بودن با running بودن یکی نیست.
- disk >= 80% هشدار؛ disk >= 90% جلوگیری از provisioning/deploy جدید. host نیز قبل از build دوباره ظرفیت را کنترل کند.
- keep=5 بودجهٔ کل releaseها با احتساب active/previous است؛ release محافظت‌شده برای رسیدن به عدد حذف نشود.
- health باید bounded، با hostname دقیق loopback، بدون redirect خارجی و با port/path معتبر باشد.
- کلیدها و credentialها در پاسخ API، HTML، log، audit، Git و metadata عمومی ذخیره نشوند.
- private repository فقط با credential model واقعی یا trusted local mapping صریح پشتیبانی شود.
- build و runtime هرگز root یا کاربر privileged Agent نباشند.
- هیچ ابزار جدید MCP در این برنامه لازم نیست؛ سازگاری قراردادهای موجود در regression حفظ شود.

## وضعیت Git؛ بررسی‌شده در این جلسه

- repository: `https://github.com/rahi62/digitalafarin-platform`
- ابتدای بررسی: `main=f76bf2950f320ca953b884c4eee1f8567091b8d2`، دو commit عقب، بدون تغییر tracked.
- Git fetch ابتدا به محدودیت نوشتن `.git` و پس از escalation به خطای DNS خورد. بنابراین ادعای fetch موفق نداریم.
- GitHub connector مستقلاً head واقعی `main` و compare را تأیید کرد؛ head همان object موجود در `origin/main` بود.
- fast-forward محلی انجام شد: `main=origin/main=46f477c0bcd79814a0960e3c1c70029d5bb49b33`؛ diverged commit یا conflict وجود نداشت.
- دو commit حفظ‌شده: `71c04f0` سلامت مسیر ریشه و `46f477c` تثبیت managed local source.
- این پنج فایل untracked قبلی دست‌نخورده ماندند: `PROMPT.md`، دو ZIP با نام‌های `stage-b3-final-027.zip` و `stage-b3-final-fix.zip`، دو patch با نام‌های `stage-b3.1-managed-deploy.patch` و `stage-b3.1-managed-deploy-v2.patch`.
- `18e3a75` در objectهای محلی موجود نیست و GitHub برای آن 422 برگرداند. با این حال منطق retention کل پنج release و تست مربوطه قبلاً در `5f56e8d` وجود دارد؛ نبودن SHA دلیل نبودن این قابلیت نیست.
- همگام‌بودن بالا مربوط به `main` است؛ branchهای تاریخی محلی جلو برده یا حذف نشدند. نسخهٔ نصب‌شده روی VPS در این ممیزی بررسی نشده است.
- این سند به صورت فایل محلی جدید باقی می‌ماند؛ commit و push انجام نشده است.

## نتیجهٔ ممیزی و شواهد

تصمیم: **NO-GO برای مدیریت کامل deployment از repository روی VPS تازه**. شواهدی از حادثهٔ فعال P0 در این بررسی محلی نداریم؛ نبود بررسی production به معنی تأیید سلامت آن نیست.

نقاط قابل‌استفاده: enrollment و credential مستقل سرور، inventory و telemetry، عملیات typed و audit، unique binding سرویس/سرور، releaseهای immutable، helper با بررسی ownership/symlink، build worker غیر root، health و rollback، رمزنگاری secret، APIهای منابع و UI پروژه‌ها. این‌ها پایهٔ قابل‌توسعه‌اند، نه یک محصول آمادهٔ انتهابه‌انتها.

| اولویت | یافته و اثر | شاهد در repository |
|---|---|---|
| P1 | ساخت Service بدون provisioning با lifecycle=managed ثبت می‌شود؛ unit جدید ساخته نمی‌شود. | `apps/api/control/deployment_serializers.py:83` و `deployment_views.py:72` |
| P1 | Agent managed فقط Next.js، بدون environment/volume را می‌پذیرد؛ انتخاب Django یا اتصال DB/variable از API به اجرای موفق منتهی نمی‌شود. | `agent/digitalafarin_agent/deployment.py:26` و `takeover_helper.py:1090` |
| P1 | helper فعلی به unit، drop-in، previous release و trusted local source موجود وابسته است؛ مسیر عمومی repo→first deployment نیست. | `takeover_helper.py:1063`، `:1122` و `:233` |
| P1 | Deploy Latest یک branch با resolved_commit خالی queue می‌کند؛ Agent SHA چهل‌رقمی اجباری می‌خواهد. تابع resolve در releases.py در این مسیر متصل نیست. | `deployment_views.py:234`، `services/execution.py:65`، `deployment.py:47` |
| P1 | heartbeat منتظر اجرای synchronous عملیات طولانی می‌ماند؛ در build طولانی سرور می‌تواند stale/offline شود. recovery فقط claim منقضی را پوشش می‌دهد، نه running رهاشده و completion گم‌شده. | `agent/digitalafarin_agent/heartbeat.py:78`، `operations.py:191`، `apps/api/control/services/operations.py:65` |
| P1 | در completion دیپلوی، تغییر domain قبل از اعتبارسنجی claim و بیرون تراکنش مشترک انجام می‌شود؛ replay موفق نیز دوباره transitionها را اعمال می‌کند. مسیر takeover الگوی امن‌تری دارد. | `apps/api/control/agent_views.py:115` و `services/deployments.py:160`؛ یافتهٔ static، سناریوی سوءاستفاده اجرا نشده است. |
| P1 | domain configure روی Agent غیر root در `/etc/nginx` می‌نویسد و reload/Certbot مستقیم اجرا می‌کند؛ unit committed اجازهٔ این نوشتن را نمی‌دهد. DB نیز psql را با هویت Agent اجرا می‌کند و دسترسی لازم در bootstrap تأمین نمی‌شود. | `agent/digitalafarin_agent/domains.py`، `postgres.py`، `infra/systemd/digitalafarin-platform-agent.service` |
| P1 | DB/Domain رکورد queued دارند، اما completion handler فعلی نتیجه را به ready/configured/ssl_enabled تبدیل نمی‌کند. موفقیت Operation کافی نیست. | `models.py:573` و `:608`، `database_views.py`، `domain_views.py`، `agent_views.py:115` |
| P1 | Add Service به migration می‌رود؛ logs و settings عمدتاً لینک/نمایش هستند و progress واقعی build وجود ندارد. eventها در انتهای اجرا برگردانده می‌شوند. | `apps/web/app/projects/[projectId]/page.tsx`، `services/[serviceId]/page.tsx` در همان پوشه، `agent/digitalafarin_agent/deployment.py` |
| P1 | baseline Agent سبز نیست؛ تغییر 46f477c استفاده از local source را اجباری کرده ولی تست prepare همچنان URL مستقیم انتظار دارد. | `agent/tests/test_managed_deployment.py:153` و diff کامیت `46f477c` |
| P2 | webhook برای repo/branch فقط اولین سرویس را انتخاب می‌کند؛ monorepo با چند سرویس نیاز به fan-out و dedup جداگانه دارد. | `apps/api/control/github_views.py:32` |
| P2 | bootstrap صرفاً readiness ابزارها/دایرکتوری‌ها را بررسی می‌کند؛ نصب کامل سرور تازه نیست. | `agent/digitalafarin_agent/bootstrap.py:21` |
| P2 | CI موجود برای Telegram تعریف شده و Agent-only changes، تست helper روی Linux و smoke provisioning را پوشش نمی‌دهد. | `.github/workflows/telegram-publisher-ci.yml` |
| P2 | backup/restore automation، alert و مدیریت نگهداری سرور کامل نیست؛ Basic Auth در Nginx جایگزین login چندکاربره نیست. | `README.md`، `infra/nginx/platform.conf.example` و نبود APIهای متناظر در `control_urls.py` |

نکتهٔ retention: helper فعال رفتار کل پنج release را دارد، اما `releases.cleanup_releases` قدیمی پنج candidate غیرمحافظت‌شده را نگه می‌دارد و README هم «پنج inactive» می‌گوید. باید قرارداد واحد شود؛ helper صحیح عقب‌گرد نکند.

## تست‌های اجراشده روی head هماهنگ‌شده

| بررسی | نتیجه |
|---|---|
| Windows API venv: `python manage.py test control.tests --noinput -v 0` | 97 تست پاس |
| `python manage.py check` | پاس |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| Web: `npm test` | 27 تست پاس |
| Web: `npm run lint` | exit 0 |
| Web: `npm run build` | exit 0؛ compilation و TypeScript پاس |
| WSL Ubuntu، محیط موجود، root برای fixtureهای ownership: `python -m pytest agent/tests -q -p no:cacheprovider` | 197 پاس، 1 شکست در `test_managed_prepare_allocates_under_root_owned_0755` |
| `git diff --check` بعد از fast-forward | پاس |

تست‌های API روی تنظیمات محلی اجرا شدند، نه اثبات concurrency روی PostgreSQL production. آزمون systemd واقعی، مرورگر E2E، acceptance سراسری، VPS و MCP در این ممیزی اجرا نشدند. تست‌های سبز حاضر بسیاری از مرزهای host را mock می‌کنند. شکست Agent باید در baseline رفع شود، نه ignore یا xfail.

## Review Focus

1. ازبین‌رفتن پاسخ پس از activation: retry باید همان نتیجه را بازیابی کند، نه unit/release دیگری بسازد؛ مالک فاز 1 و 2.
2. agent restart یا قطع شبکه وسط build: heartbeat، lease و reconciliation باید state واقعی host را بازیابی کنند؛ مالک فاز 1.
3. port/unit مشترک بین دو درخواست یا تغییر branch حین build: قفل identity، رزرو port و commit pinning؛ مالک فاز 2.
4. شکست health یا rollback همراه با تغییر env/volume: دادهٔ پایدار حذف نشود و نسخهٔ تنظیمات قبلی قابل‌بازگشت باشد؛ مالک فاز 3.
5. شکست nginx validation، restore یا گواهی: پیکربندی سالم قبلی و دادهٔ سالم حفظ شوند؛ مالک فاز 4 و 7.

## فازها و برآورد

اعداد نفرـروز مهندسی متمرکز، شامل تست و بازبینی‌اند و تعهد تقویمی نیستند. فرض: یک توسعه‌دهندهٔ آشنا با پروژه، دسترسی staging و تصمیم‌های ثابت بالا. تأخیر دسترسی، DNS، دریافت dependency و تست روی VPS می‌تواند زمان را افزایش دهد.

| فاز | خروجی قابل تحویل | نفرـروز |
|---|---|---:|
| 0 | baseline، قرارداد source/retention و CI اصلی | 1–2 |
| 1 | heartbeat مستقل، completion اتمیک، recovery و progress | 4–6 |
| 2 | public Git → سرویس Next.js واقعی با UI و rollback اولین اجرا | 6–9 |
| 3 | env/secrets و volume واقعی در release و runtime | 4–6 |
| 4 | دامنه/SSL/PostgreSQL با privilege و state صحیح | 4–6 |
| 5 | Django با migration/static/health و rollback سازگار | 4–6 |
| 6 | private Git و autodeploy قابل‌اعتماد برای monorepo | 3–5 |
| 7 | onboarding VPS، backup/restore، monitoring و maintenance | 5–8 |
| 8 | E2E واقعی، release بسته‌بندی‌شده و rollout قابل‌بازگشت | 3–5 |
| جمع | محدودهٔ داخلی تعریف‌شده | **34–53** |

با حدود 20% ذخیرهٔ خطای برآورد: **41–64 نفرـروز، تقریباً 8–13 هفته برای یک نفر**. milestone اولِ Next.js عمومی، بدون منابع پیشرفته، پس از فازهای 0–2 حدود **11–17 نفرـروز** است. برای پروژه‌های واقعی Next.js+Django با env/DB/domain، فازهای 0–5 لازم‌اند؛ private repo مرحلهٔ 6 را نیز لازم می‌کند. زمان‌ها با «یک تغییر کوچک provisioning» برابر نیستند.

## فاز 0 — baseline و جلوگیری از regression

**Files:** `agent/tests/test_managed_deployment.py`، `agent/digitalafarin_agent/takeover_helper.py`، `agent/digitalafarin_agent/releases.py`، `README.md`؛ ایجاد `.github/workflows/deployment-platform-ci.yml`.

- [ ] قرارداد source موجود را صریح کن: mapped local source برای managed فعلی حفظ شود؛ public remote مسیر مستقلی در فاز 2 داشته باشد.
- [ ] تست شکست‌خورده را به fixture واقعی local source متصل کن و تست جدا برای فقدان mapping و rejection منبع ناسازگار اضافه کن؛ assertهای ownership باقی بمانند.
- [ ] regression retention با 12 release دقیقاً 5 دایرکتوری باقی بگذارد، حتی اگر previous قدیمی است؛ آزمون symlink و current محافظت‌شده حفظ شود. README و utility قدیمی با قرارداد واحد هماهنگ شوند.
- [ ] CI برای `agent/**`، `apps/api/**`، `apps/web/**`، `infra/**` و قراردادهای مرتبط اجرا شود؛ Agent Linux، API، migration check، web test/lint/build الزامی باشند.
- [ ] full suite سبز، diff بررسی و commit مستقل baseline ساخته شود. هیچ حذف عمومی branch یا فایل untracked لازم نیست.

## فاز 1 — عملیات قابل‌بازیابی و مشاهده

**Files:** `apps/api/control/services/operations.py`، `services/deployments.py`، `agent_views.py`، `agent_urls.py`، `models.py`؛ `agent/digitalafarin_agent/heartbeat.py`، `operations.py`، `control_plane.py`؛ tests متناظر.

**Interfaces:** ادامهٔ `complete_operation(...)` موجود در یک تراکنش مشترک با result application؛ endpoint جدید `POST /api/agent/v1/operations/<operation_id>/progress` با الگوی بدون trailing slash در `agent_urls.py`. payload: claim token، sequence، stage و message پاک‌شده؛ نتیجهٔ تکراری اثر دوباره ندارد.

- [ ] تست invalid claim و duplicate completion بنویس: هیچ Deployment/Release/Event نباید با claim نامعتبر تغییر کند؛ replay دقیق نتیجهٔ موفق باید همان state را بدهد.
- [ ] validation claim، completion و domain transition را داخل یک transaction با قفل مناسب قرار بده؛ الگوی takeover موجود را reuse کن.
- [ ] worker طولانی از heartbeat مستقل شود؛ عملیات blocking در thread/process مناسب، با concurrency محدود per server و lock per service اجرا شود.
- [ ] running lease renewal، ذخیرهٔ نتیجهٔ ارسال‌نشده و reconciliation بعد از restart را اضافه کن. expiry به‌تنهایی مجوز اجرای مجدد mutation نیست؛ fencing و state واقعی helper بررسی شود.
- [ ] تست build شبیه‌سازی‌شدهٔ طولانی: در طول بیش از 120 ثانیه heartbeat ادامه یابد؛ قطع completion و restart به duplicate activation منتهی نشود.
- [ ] progress/log bounded و redacted در هنگام اجرا ارسال شود؛ UI polling با cursor واقعی داشته باشد. cancel فقط با قرارداد مشخص و cleanup امن؛ نه kill بدون reconciliation.
- [ ] PostgreSQL concurrency tests، suite Agent/API و commit مستقل.

## فاز 2 — provisioning واقعی Next.js

**Create:** `apps/api/control/services/provisioning.py`، `provisioning_views.py`، `provisioning_serializers.py`، migration بعد از `0015`؛ `agent/digitalafarin_agent/provisioning.py`، `provisioning_helper.py`؛ tests همنام؛ `apps/web/lib/provisioning.ts` و `provisioning.test.ts`؛ صفحهٔ `apps/web/app/projects/[projectId]/services/new/page.tsx`.

**Modify:** `models.py`، `control_urls.py`، `services/execution.py`، `agent_views.py`، dispatcher و helper client/server؛ `apps/web/lib/control-plane.ts`، project و service detail pages.

**Interfaces:** `POST /api/control/v1/projects/<project_id>/services/provision/` با Idempotency-Key و فقط نام، repository، branch/ref، root_directory، runtime، install/build configuration، port، target_server_id و health منطقی. خروجی HTTP 202 با service_id، provisioning_id، operation_id و state. Operation نوع `service.provision` با payload فقط provisioning_id؛ context در Control Plane ساخته شود.

**Domain:** `queue_provisioning(*, project, configuration, actor, idempotency_key)` و `apply_provisioning_result(*, operation, succeeded, result, error_code)`؛ service دارای pending/provisioning/provision_failed در کنار حالت‌های قبلی. ProvisioningRecord مستقل progress و failure را ثبت کند. مهاجرت دادهٔ سرویس‌های موجود managed را کورکورانه تغییر ندهد.

- [ ] تست API برای request صحیح، duplicate، runtime نامجاز، repository دارای credential، ref نامعتبر، `..`، absolute path، port اشغال، server offline و disk=80/90 بنویس.
- [ ] DB unique service/unit موجود حفظ شود؛ port reservation و فقط یک workflow فعال روی هر سرویس اضافه شود. نام unit از identity معتبر مشتق و با protected policy تطبیق داده شود؛ unit موجود متعلق به دیگری هرگز overwrite نشود.
- [ ] ایجاد عمومی Service دیگر managed زودهنگام نسازد؛ callerهای موجود migrate شوند و adoption جدا باقی بماند.
- [ ] source resolver دو مسیر صریح داشته باشد: public HTTPS و trusted local. branch یک‌بار به commit دقیق resolve و همان SHA persist/build شود؛ Deploy Latest موجود نیز از همین قرارداد استفاده کند. credential، local/network path و URLهای داخلی غیرمجاز reject شوند.
- [ ] helper با metadata محدود، هویت runtime policy-controlled، پورت غیرprivileged رزروشده و template ثابت unit بسازد؛ argv و executable از caller نگیرد. build و install در worker غیر root و sandbox محدود انجام شوند.
- [ ] release immutable و artifact Next.js اعتبارسنجی شود؛ current اتمیک، daemon-reload، start exact unit و health bounded اجرا شود. startup بعد از reboot نیز تست شود.
- [ ] برای web خود پلتفرم `/healthz` مستقل از redirect و صفحهٔ اصلی ایجاد شود؛ رفتار hotfix مسیر `/` تا مهاجرت تنظیم health حفظ شود. health سرویس کاربر از port/path معتبر ساخته شود و با prefix-check سادهٔ URL اعتبارسنجی نشود.
- [ ] شکست اولین activation: unit جدید stop/disable، current نامعتبر حذف/بازگردانده، release ناموفق فقط در صورت امن‌بودن پاک و خطا ثبت شود. هیچ unit قبلی یا volume حذف نشود.
- [ ] duplicate request و lost response بعد از start همان نتیجه را بازیابی کنند؛ collision و symlink escape در API و helper تست شوند.
- [ ] Add Service به wizard جدید وصل شود؛ وضعیت pending/building/health/failed/managed از backend بیاید. کاربر در خطا log و retry داشته باشد؛ managed و running مجزا نمایش داده شوند.
- [ ] gate روی VM موقت: repository عمومی نمونه از صفر به سرویس سالم برسد، commit بعدی deploy و rollback شود. Django تا فاز 5 در fresh provisioning صریحاً unsupported بماند.

## فاز 3 — env، secrets و storage قابل‌استفاده

**Files:** `environment_views.py`، `services/variables.py`، `services/execution.py`، `volume_views.py`؛ helper/provisioning/deployment؛ UI service variables/settings؛ tests منابع و managed deployment.

- [ ] version snapshot تنظیمات build/runtime را تعریف و update/delete متغیرها را با audit فقط نام کلید اضافه کن؛ نمایش secret همچنان metadata-only.
- [ ] env file خارج release، با ownership محدود و تعویض اتمیک توسط helper ایجاد شود. مسیر فایل از caller دریافت نشود. build فقط متغیرهای مجاز build را بگیرد؛ credentialهای مدیریتی مانند webhook secret به app تزریق نشوند.
- [ ] volume با logical identity به مسیر مجاز وصل شود؛ mount/ownership هر runtime مشخص باشد و link دلخواه به بیرون رد شود.
- [ ] تست پذیرش: تغییر variable در process واقعی دیده شود؛ release قدیمی تنظیمات قابل‌بازگشت داشته باشد؛ فایل upload پس از deploy/rollback باقی بماند؛ secret در log/HTML نباشد.
- [ ] health ناموفق پس از env update موجب rollback کد و configuration شود؛ storage دادهٔ پایدار rollback/delete نشود.

## فاز 4 — networking، SSL و PostgreSQL

**Files:** `agent/digitalafarin_agent/domains.py`، `postgres.py`، helper extension محدود؛ `database_views.py`، `domain_views.py`، `agent_views.py`؛ ایجاد `apps/api/control/services/resource_results.py`؛ tests و UI منابع.

**Interface:** نتیجهٔ هر Operation فقط پس از اعتبارسنجی claim و داخل transaction به resource مربوطه با همان server/project اعمال شود؛ `apply_resource_result(*, operation, succeeded, result)` idempotent باشد.

- [ ] عملیات Nginx/Certbot و DB به هویت privileged محدود مناسب منتقل شوند؛ محدودیت Agent ضعیف یا sudo عمومی اضافه نشود.
- [ ] config قبلی Nginx تا validation و reload موفق حفظ شود؛ failure به config قبلی برگردد. DNS verification، صدور/تمدید گواهی و نمایش expiry تست شوند.
- [ ] role/database مجزا، دسترسی local و credential محرمانه ایجاد شود؛ DB ready فقط پس از host success. restore روی backup ثبت‌شده و DB موردنظر با pre-backup و تأیید تخریب داده انجام شود.
- [ ] نتیجهٔ واقعی ready/configured/ssl_enabled و failure روی API/UI اعمال شود؛ replay بدون side effect تست شود.
- [ ] gate روی Linux با hardening unit واقعی: domain+TLS به برنامه برسد، DB قابل‌اتصال باشد، شکست nginx config سایت سالم قبلی را خراب نکند.

## فاز 5 — Django production runtime

**Files:** runtime template/worker جدید در Agent؛ serializers و provisioning/deployment؛ UI انتخاب runtime؛ fixture Django و tests در `acceptance/`.

- [ ] template ثابت venv، requirements، gunicorn module معتبر، collectstatic و migration policy اضافه شود؛ arbitrary pre/post shell hooks ارائه نشود.
- [ ] migration قبل از activation تنها با قواعد compatibility و lock اجرا شود. rollback کد، rollback خودکار DB فرض نشود؛ تغییرات مخرب نیازمند backup و برنامهٔ بازیابی‌اند.
- [ ] static و media از هم جدا، media روی volume پایدار و health dependency-aware باشد.
- [ ] gate: پروژهٔ واقعی Next.js + DRF + PostgreSQL از پنل provision، redeploy و recover شود؛ شکست migration سرویس سالم قبلی را خراب نکند.

## فاز 6 — private Git و autodeploy

**Files:** مدل credential/reference جدید در API؛ `github_views.py`؛ source resolver در Agent؛ UI repository و deployment settings؛ `test_github_webhook.py` و tests resolver.

- [ ] برای نسخهٔ داخلی credential مرجع رمزنگاری‌شدهٔ per-repository read-only تعریف شود؛ secret مستقیم در Service metadata قرار نگیرد. GitHub App می‌تواند مرحلهٔ بعدی باشد.
- [ ] credential کوتاه‌عمر/فایل موقت محدود به worker، حذف پس از استفاده، rotate/revoke و redact خطاهای Git تست شوند.
- [ ] webhook معتبر به همهٔ سرویس‌های مجاز repo/branch fan-out کند؛ dedup بر مبنای delivery+service و ترتیب deploy مشخص باشد. branch حذف‌شده یا SHA نامعتبر deploy نشود.
- [ ] gate: push به monorepo frontend/backend هر سرویس موردنظر را دقیقاً یک بار deploy کند؛ retry delivery و credential revoked درست مدیریت شوند.

## فاز 7 — مدیریت روزمرهٔ VPS و بازیابی

**Files:** installer جدید `infra/install-host.sh`، unitهای Agent/helper، `bootstrap.py`، server APIs/UI، ماژول‌های جدید backup/monitoring و tests.

- [ ] نصب idempotent با نسخه‌های runtime پشتیبانی‌شده، userها، permissionها، enrollment یک‌بارمصرف، helper و preflight؛ reboot و reinstall روی VPS تمیز تست شود.
- [ ] ظرفیت build/runtime، CPU/memory limits، disk/inode، log rotation، تعداد build همزمان و cleanup policy اضافه شود؛ build سنگین Control Plane را از دسترس خارج نکند.
- [ ] start/stop/restart و log روی managed unit فقط از مرز مجاز اجرا و با unit واقعی تست شود؛ maintenance mode، upgrade/rollback Agent و capability/version mismatch در UI مشخص باشند.
- [ ] backup زمان‌بندی‌شدهٔ DB/volume/Control Plane به مقصد خارج همان VPS، encryption، retention و restore drill روی سرور جدا اضافه شود. «backup successful» بدون آزمون restore معیار اتمام نیست.
- [ ] هشدار offline، disk، health و expiry با dedup و event history؛ UI آخرین نتیجه و زمان واقعی را نشان دهد.
- [ ] حذف سرویس به deprovision منطقی exact binding تبدیل شود؛ volumes و DB پیش‌فرض حفظ شوند و حذف داده عمل جداگانهٔ تأییدشده باشد.
- [ ] پنل داخلی پشت TLS+Basic Auth محدود بماند و دورزدن مستقیم port تست شود؛ اگر چند اپراتور لازم شد، login/session و actor-specific audit به scope و برآورد افزوده شود.

## فاز 8 — معیار تحویل و rollout بعدی

- [ ] تمام Agent/API/web suites، migration drift، PostgreSQL concurrency و قراردادهای موجود سبز باشند؛ CI باید شکست را متوقف کند.
- [ ] VM disposable با systemd واقعی: provisioning، bad build، bad health، restart Agent وسط build، قطع شبکه پس از activation، duplicate webhook و rollback تست شوند.
- [ ] E2E مرورگر: Add Server → Project → Repository → Configure → Deploy → Logs → Domain → Env → Redeploy → Rollback بدون ساخت دستی unit.
- [ ] امنیت مرز helper، path/symlink، عدم افشای secret، health URL parsing و quota با ورودی‌های خصمانه بررسی شود.
- [ ] بکاپ واقعی و restore روی VM دیگر؛ صورت‌جلسهٔ زمان بازیابی و میزان دادهٔ قابل‌ازدست‌رفتن ثبت شود.
- [ ] release manifest شامل SHAهای Control Plane/Agent/helper/web، schema version، OS/runtimeهای پشتیبانی‌شده و capabilityها تولید شود.
- [ ] rollout بعدی ابتدا staging؛ snapshot DB/config و release قبلی؛ ارتقای سازگار helper/Agent/API و migration طبق ماتریس نسخه؛ canary سرویس غیرحیاتی؛ health و rollback drill؛ سپس پروژه‌های اصلی.
- [ ] push، انتشار و اجرای production مرحله‌ای جدا از این ممیزی‌اند؛ در این جلسه انجام نشده‌اند.

## ترتیب شروع

شروع پیشنهادی: baseline → completion/heartbeat/recovery → provisioning عمومی Next.js. این سه فاز اولین خروجی قابل‌دیدن را می‌دهند. env/volume و Django/DB/domain باید پیش از اعلام «آماده برای پروژه‌های کامل من» تمام شوند. backlog رابط کاربری هر فاز همراه همان قابلیت تحویل شود؛ داشبورد موفقیت زودهنگام نشان ندهد.
