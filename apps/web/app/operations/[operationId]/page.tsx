import Link from "next/link";
import { getOperation } from "@/lib/control-plane";
import { OperationRefresh } from "@/components/OperationRefresh";

export const dynamic = "force-dynamic";

export default async function OperationDetailPage({ params }: { params: Promise<{ operationId: string }> }) {
  const { operationId } = await params;
  const operation = await getOperation(operationId);
  return <main className="page">
    <header className="pageHeader"><div><p className="eyebrow">OPERATION DETAIL</p><h1>{operation.kind}</h1><p className="pageLead"><code>{operation.id}</code></p></div><Link href="/operations">بازگشت</Link></header>
    <section className="panel"><div className="panelBody identityGrid">
      <OperationRefresh active={["queued", "claimed", "running"].includes(operation.state)} />
      <div className="identityField"><span>مرحلهٔ فعلی</span><code>{operation.progress?.stage || operation.state}</code></div>
      <div className="identityField"><span>State</span><code>{operation.state}</code></div>
      <div className="identityField"><span>Service</span><code>{operation.payload.unit_name}</code></div>
      <div className="identityField"><span>Error</span><code>{operation.error_code || "—"}</code></div>
      {operation.error_message ? <p role="alert">{operation.error_message}</p> : null}
      {operation.result?.logs ? <pre dir="ltr">{operation.result.logs}</pre> : null}
    </div></section>
  </main>;
}
