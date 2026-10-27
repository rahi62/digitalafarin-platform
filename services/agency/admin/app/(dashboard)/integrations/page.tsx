"use client";

import { useEffect, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { AgencyApiError, apiGet, apiMutation } from "@/lib/api";
import type { Integration, IntegrationToolDiscovery } from "@/lib/types";

const typeLabels: Record<string, string> = {
  wordpress_mcp: "WordPress MCP",
  github: "GitHub",
  gsc: "Google Search Console",
  ga4: "Google Analytics",
  other: "Other",
};

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [discoveries, setDiscoveries] = useState<Record<string, IntegrationToolDiscovery>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const { integrations: rows } = await apiGet<{ integrations: Integration[] }>("/api/v1/integrations");
      setIntegrations(rows);
      setError("");
    } catch {
      setError("خواندن Registry اتصال‌ها با خطا مواجه شد.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function healthCheck(id: string) {
    setBusyId(id);
    setError("");
    try {
      await apiMutation(`/api/v1/integrations/${id}/health-check`, "POST", {});
      await load();
    } catch (cause) {
      setError(cause instanceof AgencyApiError ? cause.message : "Health Check انجام نشد.");
    } finally {
      setBusyId(null);
    }
  }

  async function discoverTools(id: string) {
    setBusyId(id);
    setError("");
    try {
      const result = await apiMutation<{ integration: Integration; discovery: IntegrationToolDiscovery }>(
        `/api/v1/integrations/${id}/discover-tools`,
        "POST",
        {},
      );
      setDiscoveries((current) => ({ ...current, [id]: result.discovery }));
      await load();
    } catch (cause) {
      setError(cause instanceof AgencyApiError ? cause.message : "کشف ابزارهای MCP انجام نشد.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        title="اتصال‌ها"
        description="Agency مالک Connectorها نیست؛ فقط Registry، Scope و سلامت Executorهای مستقل مثل WordPress MCP و GitHub را مدیریت می‌کند."
      />

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {integrations.map((integration) => {
          const discovery = discoveries[integration.id];
          const isWordPress = integration.type === "wordpress_mcp";

          return (
            <article key={integration.id} className="surface-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-black">{integration.name}</h2>
                  <div className="mt-1 text-xs text-[var(--muted)]">{typeLabels[integration.type] ?? integration.type}</div>
                </div>
                <StatusBadge value={integration.status} />
              </div>

              <div className="mt-5 grid gap-3 rounded-xl bg-slate-50 p-4 text-xs">
                <div className="flex flex-wrap justify-between gap-2"><span className="text-[var(--muted)]">Slug</span><LtrText>{integration.slug}</LtrText></div>
                <div className="flex flex-wrap justify-between gap-2"><span className="text-[var(--muted)]">Endpoint</span><LtrText className="max-w-full break-all">{integration.endpoint || "—"}</LtrText></div>
                <div className="flex flex-wrap justify-between gap-2"><span className="text-[var(--muted)]">آخرین Health Check</span><span>{integration.lastHealthAt ? new Date(integration.lastHealthAt).toLocaleString("fa-IR") : "ثبت نشده"}</span></div>
                <div className="flex flex-wrap justify-between gap-2"><span className="text-[var(--muted)]">آخرین موفقیت</span><span>{integration.lastSuccessAt ? new Date(integration.lastSuccessAt).toLocaleString("fa-IR") : "ثبت نشده"}</span></div>
              </div>

              {isWordPress ? (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-900">
                  حالت این اتصال در Agency فعلاً <strong>فقط خواندنی</strong> است. Discovery فقط فهرست ابزارهای MCP را می‌خواند و هیچ ابزار وردپرسی را اجرا نمی‌کند.
                </div>
              ) : null}

              {discovery ? (
                <div className="mt-4 rounded-xl border border-[var(--border)] bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs text-[var(--muted)]">ابزارهای کشف‌شده</div>
                      <div className="mt-1 text-sm font-black">{discovery.toolCount.toLocaleString("fa-IR")} ابزار</div>
                    </div>
                    <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-black text-emerald-700">Read-only</span>
                  </div>
                  <div className="mt-3 max-h-72 space-y-2 overflow-auto">
                    {discovery.tools.map((tool) => (
                      <div key={tool.name} className="rounded-lg bg-slate-50 p-3 text-xs">
                        <LtrText className="font-bold text-slate-800">{tool.name}</LtrText>
                        {tool.description ? <p className="mt-1 leading-5 text-[var(--muted)]">{tool.description}</p> : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => healthCheck(integration.id)}
                  disabled={busyId === integration.id}
                  className="rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {busyId === integration.id ? "در حال بررسی…" : "بررسی سلامت"}
                </button>
                {isWordPress ? (
                  <button
                    type="button"
                    onClick={() => discoverTools(integration.id)}
                    disabled={busyId === integration.id}
                    className="rounded-xl bg-slate-950 px-3 py-2 text-xs font-black text-white hover:bg-slate-800 disabled:opacity-50"
                  >
                    {busyId === integration.id ? "در حال اتصال…" : "کشف ابزارهای MCP"}
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
        {!integrations.length && !error ? <div className="surface-card col-span-full p-8 text-center text-sm text-[var(--muted)]">Integrationی در Registry ثبت نشده است.</div> : null}
      </div>
    </div>
  );
}
