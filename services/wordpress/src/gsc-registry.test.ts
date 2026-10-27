import assert from "node:assert/strict";
import test from "node:test";
import { listGscSites } from "./gsc-registry.js";

test("gsc_list_sites reads registry mappings without treating them as OAuth health", async (t) => {
  const originalFetch = globalThis.fetch;
  let requests = 0;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async () => {
    requests += 1;
    return new Response(JSON.stringify({ sites: [{
      id: "44cd0ec6-5663-48a9-ad56-49c945b27206",
      name: "vammelki24",
      baseUrl: "https://vammelki24.com",
      propertyUrl: "sc-domain:vammelki24.com",
    }] }), { status: 200, headers: { "Content-Type": "application/json" } });
  };

  const sites = await listGscSites();

  assert.equal(requests, 1);
  assert.equal(sites[0]?.propertyUrl, "sc-domain:vammelki24.com");
});
