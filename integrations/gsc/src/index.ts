import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { googleRead, propertyUrl } from "./google-api.js";

// Initial standalone transport. Account authorization via the settings UI
// is a separate prerequisite; never put refresh tokens into source code.
const token = process.env.GSC_ACCESS_TOKEN?.trim();
if (!token) {
  console.error("GSC account not configured. Complete local account setup before starting MCP.");
  process.exit(1);
}
const mcp = new McpServer({ name:"DigitalAfarin GSC", version:"0.1.0" });
const readOnly = { readOnlyHint:true, destructiveHint:false, openWorldHint:true };
function result(value: unknown) { return {content:[{type:"text" as const,text:JSON.stringify(value)}]}; }
function failure(error: unknown) { return {content:[{type:"text" as const,text:error instanceof Error ? error.message : "GSC request failed"}],isError:true}; }
mcp.registerTool("gsc_list_properties",{title:"List GSC properties",description:"Read properties accessible to the Google account",inputSchema:{},annotations:readOnly},async()=>{
  try { return result(await googleRead(token!,"https://www.googleapis.com/webmasters/v3/sites")); } catch(e){return failure(e);}
});
mcp.registerTool("gsc_search_performance",{title:"Read GSC search performance",description:"Read raw performance metrics; Claude performs analysis and comparisons",inputSchema:{
 property:z.string().min(3).max(2048),
 startDate:z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
 endDate:z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
 dimensions:z.array(z.enum(["query","page","date","country","device","searchAppearance"])).max(6).optional(),
 rowLimit:z.number().int().min(1).max(25000).default(1000),
 startRow:z.number().int().min(0).default(0)
},annotations:readOnly},async({property,startDate,endDate,dimensions,rowLimit,startRow})=>{
 try{
 if(startDate>endDate) throw new Error("Invalid date range");
 return result(await googleRead(token!,`https://www.googleapis.com/webmasters/v3/sites/${propertyUrl(property)}/searchAnalytics/query`,{startDate,endDate,dimensions,rowLimit,startRow,type:"web",dataState:"final"}));
 } catch(e){return failure(e);}
});
await mcp.connect(new StdioServerTransport());
