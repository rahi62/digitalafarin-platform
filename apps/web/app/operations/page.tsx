import Link from "next/link";
import { listOperations, listServers, listServices } from "@/lib/control-plane";
import { queueServiceOperation } from "./actions";

export const dynamic = "force-dynamic";

export default async function OperationsPage() {
  const [operations, servers] = await Promise.all([
    listOperations().catch(() => []),
    listServers().catch(() => []),
  ]);
  const server = servers.find((item) => item.is_default) ?? servers[0];
  const services = server ? await listServices(server.id).catch(() => []) : [];
  const mutable = services.filter((item) => !item.unit_name.startsWith("digitalafarin-platform-"));
  return <main className="page">
    <header className="pageHeader"><div><p className="eyebrow">TYPED OPERATIONS</p><h1>عملیات</h1><p className="pageLead">عملیات محدود و audit‌شده؛ بدون shell یا systemctl آزاد.</p></div></header>
    {server && mutable.length ? <section className="panel" style={{ marginBottom: 12 }}>
      <div className="panelHeader"><div><h2>ایجاد عملیات</h2><p>{server.name}</p></div></div>
      <form className="filterBar" action={queueServiceOperation}>
        <input type="hidden" name="server_id" value={server.id} />
        <label><span>سرویس</span><select name="unit_name">{mutable.map((item) => <option key={item.unit_name}>{item.unit_name}</option>)}</select></label>
        <label><span>عملیات</span><select name="action"><option value="restart">Restart</option><option value="start">Start</option><option value="stop">Stop</option><option value="logs">Logs</option></select></label>
        <button type="submit">Queue</button>
      </form>
    </section> : null}
    <section className="panel"><div className="panelHeader"><div><h2>تاریخچه</h2><p>{operations.length} عملیات اخیر</p></div></div>
      <div className="tableWrap"><table className="dataTable"><thead><tr><th>نوع</th><th>سرویس</th><th>وضعیت</th><th>زمان</th></tr></thead><tbody>
        {operations.map((item) => <tr key={item.id}><td><Link href={`/operations/${item.id}`}>{item.kind}</Link></td><td><code>{item.payload.unit_name}</code></td><td>{item.state}</td><td dir="ltr">{new Date(item.created_at).toLocaleString()}</td></tr>)}
      </tbody></table></div>
    </section>
  </main>;
}
