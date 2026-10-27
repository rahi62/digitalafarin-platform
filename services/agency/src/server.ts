import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { agencyTeam, operatingPolicy } from "./team.js";
import { addNote, createTask, getProject, listProjects, recordDecision, updateTask, upsertProject } from "./store.js";

export const agencyToolNames = [
  "agency_get_team",
  "agency_prepare_council",
  "agency_list_projects",
  "agency_get_project",
  "agency_upsert_project",
  "agency_add_note",
  "agency_record_decision",
  "agency_create_task",
  "agency_update_task",
] as const;

function text(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

function failure(error: unknown) {
  return { ...text({ error: error instanceof Error ? error.message : "Unexpected error" }), isError: true };
}

const projectId = z.string().uuid();
const projectSlug = z.string().trim().min(1).max(200).regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);

export function createMcpServer() {
  const server = new McpServer({ name: "DigitalAfarin Agency", version: "0.2.0" });

  server.registerTool("agency_get_team", {
    title: "Get DigitalAfarin virtual agency team",
    description: "Return the specialist roster and operating policy. Use this before a council/brainstorm so ChatGPT can reason as the relevant specialists.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async () => text({ team: agencyTeam, operatingPolicy }));

  server.registerTool("agency_prepare_council", {
    title: "Prepare an agency council",
    description: "Load a project's context plus selected specialist roles for a strategy or problem-solving council. This tool does not call another LLM; ChatGPT should perform the specialist reasoning itself.",
    inputSchema: {
      projectId,
      topic: z.string().trim().min(3).max(3000),
      specialistIds: z.array(z.string()).max(13).optional(),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async ({ projectId, topic, specialistIds }) => {
    try {
      const project = await getProject(projectId);
      if (!project) throw new Error("Project not found");
      const specialists = specialistIds?.length ? agencyTeam.filter((a) => specialistIds.includes(a.id)) : agencyTeam;
      return text({
        topic,
        project,
        specialists,
        operatingPolicy,
        instruction: "Each relevant specialist should assess the topic independently. Chief of Staff then synthesizes disagreements into priorities, risks and next actions.",
      });
    } catch (e) {
      return failure(e);
    }
  });

  server.registerTool("agency_list_projects", {
    title: "List agency projects",
    description: "List projects registered in DigitalAfarin Agency memory.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async () => text({ projects: await listProjects() }));

  server.registerTool("agency_get_project", {
    title: "Get project context",
    description: "Read the complete stored context, notes, decisions and tasks for one DigitalAfarin project.",
    inputSchema: { projectId },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async ({ projectId }) => text({ project: await getProject(projectId) }));

  server.registerTool("agency_upsert_project", {
    title: "Create or update agency project",
    description: "Create a project or update its durable context in the Agency connector. Slug is optional and backward-compatible.",
    inputSchema: {
      id: projectId.optional(),
      name: z.string().trim().min(1).max(200),
      slug: projectSlug.optional(),
      description: z.string().max(5000).optional(),
      goals: z.array(z.string().max(1000)).max(30).optional(),
      stack: z.array(z.string().max(100)).max(30).optional(),
      links: z.record(z.string().max(100), z.string().max(2000)).optional(),
      status: z.enum(["active", "paused", "archived"]).optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async (input) => {
    try {
      return text({ project: await upsertProject(input) });
    } catch (e) {
      return failure(e);
    }
  });

  server.registerTool("agency_add_note", {
    title: "Add project memory note",
    description: "Persist an important project fact, constraint, finding or context note.",
    inputSchema: { projectId, text: z.string().trim().min(1).max(10000) },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async ({ projectId, text: note }) => {
    try {
      return text({ note: await addNote(projectId, note) });
    } catch (e) {
      return failure(e);
    }
  });

  server.registerTool("agency_record_decision", {
    title: "Record agency decision",
    description: "Persist a decision and its rationale so later chats can recover why it was made.",
    inputSchema: {
      projectId,
      title: z.string().trim().min(1).max(300),
      decision: z.string().trim().min(1).max(10000),
      rationale: z.string().max(10000).optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async ({ projectId, title, decision, rationale }) => {
    try {
      return text({ decision: await recordDecision(projectId, title, decision, rationale) });
    } catch (e) {
      return failure(e);
    }
  });

  server.registerTool("agency_create_task", {
    title: "Create agency task",
    description: "Create an execution task for a project after a discussion or council decision.",
    inputSchema: {
      projectId,
      title: z.string().trim().min(1).max(300),
      details: z.string().max(10000).optional(),
      priority: z.enum(["low", "medium", "high", "critical"]).optional(),
      owner: z.string().max(100).optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async ({ projectId, ...input }) => {
    try {
      return text({ task: await createTask(projectId, input) });
    } catch (e) {
      return failure(e);
    }
  });

  server.registerTool("agency_update_task", {
    title: "Update agency task",
    description: "Update status, owner, details or priority of an existing project task.",
    inputSchema: {
      projectId,
      taskId: z.string().uuid(),
      status: z.enum(["todo", "doing", "done", "blocked"]).optional(),
      priority: z.enum(["low", "medium", "high", "critical"]).optional(),
      owner: z.string().max(100).optional(),
      details: z.string().max(10000).optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async ({ projectId, taskId, ...patch }) => {
    try {
      return text({ task: await updateTask(projectId, taskId, patch) });
    } catch (e) {
      return failure(e);
    }
  });

  return server;
}
