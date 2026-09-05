export type ApiErrorPayload = { code: string; message: string };
export type ApiEnvelope<T> = { data: T | null; error: ApiErrorPayload | null };

export type CurrentUser = {
  userId?: string;
  id?: string;
  email: string;
  displayName: string;
};

export type ProjectHealth = "healthy" | "attention" | "at_risk" | "critical";
export type Priority = "low" | "medium" | "high" | "critical";
export type TaskStatus = "todo" | "doing" | "done" | "blocked";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export type Project = {
  id: string;
  name: string;
  slug: string;
  type?: "internal" | "client";
  status: "active" | "paused" | "archived";
  health?: ProjectHealth;
  priority?: Priority;
  description?: string | null;
  summary?: string | null;
  goals: string[];
  stack: string[];
  links: Record<string, string>;
  createdAt?: string;
  updatedAt: string;
  noteCount?: number;
  decisionCount?: number;
  taskCount?: number;
  tasks?: Task[] | ProjectTask[];
  decisions?: Decision[];
  notes?: Note[];
};

export type ProjectTask = {
  id: string;
  title: string;
  status: TaskStatus;
  priority: Priority;
  owner?: string;
  details?: string;
  createdAt: string;
  updatedAt: string;
};

export type Task = {
  id: string;
  projectId: string;
  departmentId?: string | null;
  title: string;
  description?: string | null;
  status: TaskStatus;
  priority: Priority;
  riskLevel: RiskLevel;
  ownerLabel?: string | null;
  executorType: "manual" | "wordpress_mcp" | "github" | "automation" | "other";
  approvalRequired: boolean;
  expectedImpact?: string | null;
  effort?: string | null;
  dueDate?: string | null;
  updatedAt: string;
};

export type Decision = {
  id: string;
  title: string;
  decision: string;
  rationale?: string | null;
  createdAt: string;
};

export type Note = { id: string; text: string; createdAt: string };

export type Department = {
  id: string;
  slug: string;
  name: string;
  mission?: string | null;
  status: "active" | "paused" | "archived";
  roles?: Array<{ id: string; slug: string; name: string; mission?: string | null; responsibilities?: string[] | null }>;
  tasks?: Task[];
  workflows?: Array<{ id: string; slug: string; name: string; description?: string | null; status: string; steps?: unknown[] }>;
};

export type Approval = {
  id: string;
  projectId: string;
  taskId?: string | null;
  actionType: string;
  riskLevel: RiskLevel;
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled";
  reason?: string | null;
  payload: Record<string, unknown>;
  diffPreview?: Record<string, unknown> | null;
  requestedAt: string;
  reviewedAt?: string | null;
};

export type Activity = {
  id: string;
  actorType: "user" | "chatgpt" | "system" | "integration";
  actorLabel?: string | null;
  projectId?: string | null;
  entityType: string;
  entityId?: string | null;
  action: string;
  summary: string;
  createdAt: string;
};

export type Integration = {
  id: string;
  slug: string;
  name: string;
  type: "wordpress_mcp" | "github" | "gsc" | "ga4" | "other";
  status: "connected" | "degraded" | "disconnected" | "disabled";
  endpoint?: string | null;
  lastHealthAt?: string | null;
  lastSuccessAt?: string | null;
};

export type IntegrationToolDiscovery = {
  endpoint: string;
  mode: "read_only";
  toolCount: number;
  tools: Array<{ name: string; description?: string }>;
};

export type DashboardSummary = {
  counters: {
    activeProjects: number;
    criticalTasks: number;
    blockedTasks: number;
    pendingApprovals: number;
  };
  projectHealth: Array<{ id: string; name: string; slug: string; health: ProjectHealth; priority: Priority }>;
  departmentWorkload: Array<{ id: string; slug: string; name: string; openTasks: number; blockedTasks: number }>;
  recentActivity: Activity[];
  upcomingDeadlines: Task[];
};
