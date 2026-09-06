import type { CSSProperties } from "react";

import {
  createChannelAction,
  setBotTokenAction,
  testChannelAction,
  toggleChannelAction,
  updateChannelAction,
} from "./actions";
import {
  getTelegramStatus,
  listTelegramAudit,
  listTelegramChannels,
} from "@/lib/telegram";

export const dynamic = "force-dynamic";

const inputStyle: CSSProperties = {
  width: "100%",
  border: "1px solid var(--border, #d8dee9)",
  borderRadius: 10,
  padding: "10px 12px",
  background: "var(--surface, #fff)",
  color: "inherit",
  font: "inherit",
};

const buttonStyle: CSSProperties = {
  border: 0,
  borderRadius: 10,
  padding: "10px 14px",
  cursor: "pointer",
  font: "inherit",
  fontWeight: 700,
};

const gridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: 12,
};

function field(label: string, name: string, options: { type?: string; placeholder?: string; defaultValue?: string; required?: boolean } = {}) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span style={{ fontSize: 13, fontWeight: 700 }}>{label}</span>
      <input
        style={inputStyle}
        name={name}
        type={options.type ?? "text"}
        placeholder={options.placeholder}
        defaultValue={options.defaultValue}
        required={options.required}
        autoComplete={options.type === "password" ? "new-password" : undefined}
      />
    </label>
  );
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat("fa-IR", {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: "Asia/Tehran",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function TelegramBotAdmin({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const notice = typeof params.notice === "string" ? params.notice : null;
  const error = typeof params.error === "string" ? params.error : null;

  const [statusResult, channelsResult, auditResult] = await Promise.allSettled([
    getTelegramStatus(),
    listTelegramChannels(),
    listTelegramAudit(25),
  ]);

  const status = statusResult.status === "fulfilled" ? statusResult.value : null;
  const channels = channelsResult.status === "fulfilled" ? channelsResult.value : [];
  const audits = auditResult.status === "fulfilled" ? auditResult.value : [];
  const apiDown = statusResult.status === "rejected" || channelsResult.status === "rejected";

  return (
    <main className="page" dir="rtl">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">TELEGRAM PUBLISHER</p>
          <h1>مدیریت انتشار تلگرام</h1>
          <p className="pageLead">
            ربات، کانال‌ها و دسترسی انتشار ChatGPT را از یک پنل مرکزی مدیریت کن.
          </p>
        </div>
        <div className="pageActions">
          <span
            style={{
              borderRadius: 999,
              padding: "8px 12px",
              fontWeight: 800,
              background: status?.bot_configured ? "rgba(22, 163, 74, .12)" : "rgba(245, 158, 11, .16)",
            }}
          >
            {status?.bot_configured ? "Bot configured" : "Bot not configured"}
          </span>
        </div>
      </header>

      {notice ? <div className="notice" style={{ marginBottom: 12 }}>{notice}</div> : null}
      {error ? (
        <div className="notice" style={{ marginBottom: 12, borderColor: "rgba(220, 38, 38, .35)" }}>
          {error}
        </div>
      ) : null}
      {apiDown ? (
        <section className="panel errorPanel" style={{ marginBottom: 12 }}>
          <div className="panelBody">
            <strong>Telegram Control Plane در دسترس نیست.</strong>
            <p>Service Principal پنل و سرویس Django را بررسی کن.</p>
          </div>
        </section>
      ) : null}

      <div className="metricsGrid">
        <section className="panel" style={{ padding: 18 }}>
          <p className="eyebrow">BOT</p>
          <strong style={{ fontSize: 22 }}>{status?.bot_configured ? "آماده" : "نیاز به توکن"}</strong>
          <p style={{ marginBottom: 0, opacity: .72 }}>{status?.bot_name ?? "primary"}</p>
        </section>
        <section className="panel" style={{ padding: 18 }}>
          <p className="eyebrow">ACTIVE CHANNELS</p>
          <strong style={{ fontSize: 28 }}>{status?.active_channels ?? 0}</strong>
          <p style={{ marginBottom: 0, opacity: .72 }}>کانال فعال</p>
        </section>
        <section className="panel" style={{ padding: 18 }}>
          <p className="eyebrow">MCP</p>
          <strong style={{ fontSize: 22 }}>Port 3061</strong>
          <p style={{ marginBottom: 0, opacity: .72 }}>localhost-only /mcp</p>
        </section>
      </div>

      <div className="sectionGrid" style={{ marginTop: 12 }}>
        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>تنظیم ربات</h2>
              <p>توکن فعلی هیچ‌وقت از سرور خوانده یا نمایش داده نمی‌شود.</p>
            </div>
          </div>
          <form action={setBotTokenAction} className="panelBody" style={{ display: "grid", gap: 12 }}>
            {field("نام تنظیم", "name", { defaultValue: status?.bot_name ?? "primary", required: true })}
            {field("Bot Token جدید", "token", { type: "password", placeholder: "123456789:AA...", required: true })}
            <button style={{ ...buttonStyle, background: "#111827", color: "white", justifySelf: "start" }} type="submit">
              اعتبارسنجی و ذخیره توکن
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>افزودن کانال</h2>
              <p>Alias همان نام کوتاهی است که در ChatGPT استفاده می‌کنی.</p>
            </div>
          </div>
          <form action={createChannelAction} className="panelBody" style={{ display: "grid", gap: 12 }}>
            <div style={gridStyle}>
              {field("Alias", "alias", { placeholder: "seo", required: true })}
              {field("نام نمایشی", "name", { placeholder: "DigitalAfarin SEO", required: true })}
            </div>
            {field("Chat ID یا @username", "chat_id", { placeholder: "@digitalafarin_seo یا -100...", required: true })}
            {field("توضیح", "description", { placeholder: "محتوای سئو" })}
            <button style={{ ...buttonStyle, background: "#2563eb", color: "white", justifySelf: "start" }} type="submit">
              افزودن کانال
            </button>
          </form>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 12 }}>
        <div className="panelHeader">
          <div>
            <h2>کانال‌ها</h2>
            <p>{channels.length} کانال ثبت شده؛ فقط کانال‌های فعال برای MCP قابل انتشارند.</p>
          </div>
        </div>
        <div className="panelBody" style={{ display: "grid", gap: 12 }}>
          {channels.length === 0 ? (
            <p style={{ opacity: .7 }}>هنوز کانالی اضافه نشده است.</p>
          ) : channels.map((channel) => (
            <article
              key={channel.id}
              style={{
                border: "1px solid var(--border, #e5e7eb)",
                borderRadius: 14,
                padding: 14,
                display: "grid",
                gap: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <strong dir="ltr">{channel.alias}</strong>
                  <span style={{ marginInlineStart: 10, opacity: .7 }}>{channel.name}</span>
                </div>
                <span style={{ fontWeight: 800, opacity: channel.is_active ? 1 : .55 }}>
                  {channel.is_active ? "فعال" : "غیرفعال"}
                </span>
              </div>

              <form action={updateChannelAction} style={{ display: "grid", gap: 10 }}>
                <input type="hidden" name="id" value={channel.id} />
                <input type="hidden" name="is_active" value={String(channel.is_active)} />
                <div style={gridStyle}>
                  {field("Alias", "alias", { defaultValue: channel.alias, required: true })}
                  {field("نام", "name", { defaultValue: channel.name, required: true })}
                  {field("Chat ID", "chat_id", { defaultValue: channel.chat_id, required: true })}
                  {field("توضیح", "description", { defaultValue: channel.description })}
                </div>
                <button style={{ ...buttonStyle, background: "rgba(37, 99, 235, .12)", justifySelf: "start" }} type="submit">
                  ذخیره تغییرات
                </button>
              </form>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <form action={testChannelAction}>
                  <input type="hidden" name="id" value={channel.id} />
                  <input type="hidden" name="alias" value={channel.alias} />
                  <button style={{ ...buttonStyle, background: "rgba(16, 185, 129, .14)" }} type="submit" disabled={!channel.is_active || !status?.bot_configured}>
                    ارسال پیام تست
                  </button>
                </form>
                <form action={toggleChannelAction}>
                  <input type="hidden" name="id" value={channel.id} />
                  <input type="hidden" name="alias" value={channel.alias} />
                  <input type="hidden" name="next_active" value={String(!channel.is_active)} />
                  <button style={{ ...buttonStyle, background: "rgba(107, 114, 128, .12)" }} type="submit">
                    {channel.is_active ? "غیرفعال کن" : "فعال کن"}
                  </button>
                </form>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <div className="panelHeader">
          <div>
            <h2>آخرین عملیات تلگرام</h2>
            <p>Audit انتشار و تست؛ متن کامل پیام در audit ذخیره نمی‌شود.</p>
          </div>
        </div>
        <div className="panelBody" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
            <thead>
              <tr style={{ textAlign: "right", opacity: .7 }}>
                <th style={{ padding: 10 }}>زمان</th>
                <th style={{ padding: 10 }}>کانال</th>
                <th style={{ padding: 10 }}>عملیات</th>
                <th style={{ padding: 10 }}>وضعیت</th>
                <th style={{ padding: 10 }}>Actor</th>
                <th style={{ padding: 10 }}>خلاصه</th>
              </tr>
            </thead>
            <tbody>
              {audits.map((audit) => (
                <tr key={audit.id} style={{ borderTop: "1px solid var(--border, #e5e7eb)" }}>
                  <td style={{ padding: 10, whiteSpace: "nowrap" }}>{formatDate(audit.created_at)}</td>
                  <td style={{ padding: 10 }} dir="ltr">{audit.channel ?? "—"}</td>
                  <td style={{ padding: 10 }}>{audit.action}</td>
                  <td style={{ padding: 10, fontWeight: 800 }}>{audit.status}</td>
                  <td style={{ padding: 10 }} dir="ltr">{audit.actor_principal}</td>
                  <td style={{ padding: 10, maxWidth: 320 }}>{audit.error_message || audit.content_preview || "—"}</td>
                </tr>
              ))}
              {audits.length === 0 ? (
                <tr><td colSpan={6} style={{ padding: 18, opacity: .7 }}>هنوز audit تلگرامی ثبت نشده است.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
