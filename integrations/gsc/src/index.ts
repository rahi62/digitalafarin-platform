import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { googleRead, propertyUrl } from "./google-api.js";

// Initial standalone transport. Account authorization via the settings UI
// is a separate prerequisite; never put refresh tokens into source code.
import { load, unprotect, googleToken } from "./accounts.js";
import { runSettings } from "./settings.js";

if (process.argv[2] === "settings") {
  await runSettings();
} else {
const accounts = await load();
if (!accounts.accounts.length) {
  console.error("No Google account connected. Run: npm run settings");
  process.exit(1);
}
async function access(accountId: string): Promise<string> {
  const settings = await load();
  const account = settings.accounts.find((value) => value.id === accountId);
  if (!account) throw new Error("Account not found. Check gsc_list_accounts.");
  return googleToken(settings.clientId, await unprotect(account.encryptedRefreshToken));
}
const mcp = new McpServer({ name:"DigitalAfarin GSC", version:"0.1.0" });
const readOnly = { readOnlyHint:true, destructiveHint:false, openWorldHint:true };
function result(value: unknown) { return {content:[{type:"text" as const,text:JSON.stringify(value)}]}; }
function failure(error: unknown) { return {content:[{type:"text" as const,text:error instanceof Error ? error.message : "GSC request failed"}],isError:true}; }
mcp.registerTool("gsc_list_accounts",{title:"List connected Google accounts",description:"List local account identifiers without credentials",inputSchema:{},annotations:readOnly},async()=>{const s=await load();return result({accounts:s.accounts.map(({id,label})=>({id,label}))});});
mcp.registerTool("gsc_list_properties",{title:"List GSC properties",description:"Read properties accessible to the Google account",inputSchema:{accountId:z.string().min(1)},annotations:readOnly},async({accountId})=>{
  try { return result(await googleRead(await access(accountId),"https://www.googleapis.com/webmasters/v3/sites")); } catch(e){return failure(e);}
});
mcp.registerTool("gsc_search_performance",{title:"Read GSC search performance",description:"Read raw performance metrics; Claude performs analysis and comparisons",inputSchema:{
 accountId:z.string().min(1),
 property:z.string().min(3).max(2048),
 startDate:z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
 endDate:z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
 dimensions:z.array(z.enum(["query","page","date","country","device","searchAppearance"])).max(6).optional(),
 rowLimit:z.number().int().min(1).max(25000).default(1000),
 startRow:z.number().int().min(0).default(0),
 filters:z.array(z.object({dimension:z.enum(["query","page","country","device","searchAppearance"]),operator:z.enum(["equals","contains","notEquals","notContains","includingRegex","excludingRegex"]).default("equals"),expression:z.string().min(1).max(4096)})).max(20).optional()
},annotations:readOnly},async({accountId,property,startDate,endDate,dimensions,rowLimit,startRow,filters})=>{
 try{
 if(startDate>endDate) throw new Error("Invalid date range");
 return result(await googleRead(await access(accountId),`https://www.googleapis.com/webmasters/v3/sites/${propertyUrl(property)}/searchAnalytics/query`,{startDate,endDate,dimensions,rowLimit,startRow,type:"web",dataState:"final",...(filters?.length?{dimensionFilterGroups:[{groupType:"and",filters}]}:{})}));
 } catch(e){return failure(e);}
});
mcp.registerTool("gsc_list_sitemaps", {
 title:"List GSC sitemaps",description:"Read submitted sitemaps for a Search Console property",
 inputSchema:{accountId:z.string().min(1),property:z.string().min(3).max(2048)},annotations:readOnly
},async({accountId,property})=>{
 try{return result(await googleRead(await access(accountId),`https://www.googleapis.com/webmasters/v3/sites/${propertyUrl(property)}/sitemaps`));}
 catch(e){return failure(e);}
});
mcp.registerTool("gsc_inspect_url", {
 title:"Inspect indexed URL",description:"Read the last known Google index status for a URL; does not request indexing",
 inputSchema:{accountId:z.string().min(1),property:z.string().min(3).max(2048),inspectionUrl:z.string().url().max(2048)},annotations:readOnly
},async({accountId,property,inspectionUrl})=>{
 try{return result(await googleRead(await access(accountId),"https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",{inspectionUrl,siteUrl:property}));}
 catch(e){return failure(e);}
});
await mcp.connect(new StdioServerTransport());
}
