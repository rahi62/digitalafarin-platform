import Link from "next/link";
import { getOperation } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function OperationDetailPage({ params }: { params: Promise<{ operationId: string }> }) {
  const { operationId } = await params;
  const operation = await getOperation(operationId);
  return <main className="page">
    <header className="pageHeader"><div><p className="eyebrow">OPERATION DETAIL</p><h1>{operation.kind}</h1><p className="pageLead"><code>{operation.id}</code></p></div><Link href="/operations">بازگشت</Link></header>
    <section className="panel"><div className="panelBody identityGrid">
      <div className="identityField"><span>State</span><code>{operation.state}</code></div>
      <div className="identityField"><span>Service</span><code>{operation.payload.unit_name}</code></div>
      <div className="identityField"><span>Error</span><code>{operation.error_code || "—"}</code></div>
      {operation.result?.logs ? <pre dir="ltr">{operation.result.logs}</pre> : null}
    </div></section>
  </main>;
}
