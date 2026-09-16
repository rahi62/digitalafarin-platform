import {
  deriveMigrationReadiness,
  type MigrationProjectInput,
  type MigrationReadinessContext,
  type MigrationServerInput,
  type ReadinessStep,
} from "./migration-readiness.ts";

type MigrationPageDependencies = {
  listServers: () => Promise<Array<MigrationServerInput & { id: string }>>;
  listProjects: () => Promise<Array<{ id: string }>>;
  getProject: (projectId: string) => Promise<MigrationProjectInput>;
  listOperations: () => Promise<NonNullable<MigrationReadinessContext["operations"]>>;
  getMetrics: (serverId: string) => Promise<NonNullable<MigrationReadinessContext["metrics"]>[number]>;
  listDeployments: (serviceId: string) => Promise<NonNullable<MigrationReadinessContext["deployments"]>>;
};

export async function loadMigrationReadiness(dependencies: MigrationPageDependencies): Promise<ReadinessStep[]> {
  const [servers, projectSummaries, operations] = await Promise.all([
    dependencies.listServers(),
    dependencies.listProjects(),
    dependencies.listOperations(),
  ]);
  const projects = await Promise.all(projectSummaries.map((project) => dependencies.getProject(project.id)));
  const services = projects.flatMap((project) => project.services ?? []);
  const [metrics, deploymentGroups] = await Promise.all([
    Promise.all(servers.map(async (server) => {
      try {
        return await dependencies.getMetrics(server.id);
      } catch {
        return { id: server.id, disk_percent: 0, stale: true };
      }
    })),
    Promise.all(services.map((service) => dependencies.listDeployments(service.id))),
  ]);

  return deriveMigrationReadiness(servers, projects, {
    operations,
    deployments: deploymentGroups.flat(),
    metrics,
  });
}
