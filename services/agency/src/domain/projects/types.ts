export type ProjectStatus = "active" | "paused" | "archived";
export type TaskStatus = "todo" | "doing" | "done" | "blocked";
export type Priority = "low" | "medium" | "high" | "critical";

export type ProjectNote = {
  id: string;
  text: string;
  createdAt: string;
};

export type ProjectDecision = {
  id: string;
  title: string;
  decision: string;
  rationale?: string;
  createdAt: string;
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

export type ProjectSnapshot = {
  id: string;
  name: string;
  slug?: string;
  description?: string;
  status: ProjectStatus;
  goals: string[];
  stack: string[];
  links: Record<string, string>;
  notes: ProjectNote[];
  decisions: ProjectDecision[];
  tasks: ProjectTask[];
  createdAt: string;
  updatedAt: string;
};

export type ProjectListItem = Omit<ProjectSnapshot, "notes" | "decisions" | "tasks"> & {
  noteCount: number;
  decisionCount: number;
  taskCount: number;
};

export type UpsertProjectInput = {
  id?: string;
  name: string;
  slug?: string;
  description?: string;
  goals?: string[];
  stack?: string[];
  links?: Record<string, string>;
  status?: ProjectStatus;
};

export type CreateTaskInput = {
  title: string;
  details?: string;
  priority?: Priority;
  owner?: string;
};

export type UpdateTaskPatch = {
  status?: TaskStatus;
  priority?: Priority;
  owner?: string;
  details?: string;
};
