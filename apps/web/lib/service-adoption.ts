export type ServiceLifecycle = "adopted" | "configured" | "managed";
export type ServiceRuntime = "node-nextjs" | "python-django";

const unitPattern = /^[A-Za-z0-9_.@:-]+\.service$/;
const slugPattern = /^[A-Za-z0-9_-]{1,80}$/;

export function buildAdoptServiceRequest(serverId: string, unitName: string, name: string) {
  if (!serverId || !unitPattern.test(unitName) || !slugPattern.test(name)) {
    throw new Error("Invalid service adoption input");
  }
  return { server_id: serverId, unit_name: unitName, name };
}

export function buildDeploymentConfigurationRequest(input: {
  repository: string;
  branch: string;
  rootDirectory: string;
  runtime: ServiceRuntime;
  servicePort: number;
  installConfiguration: Record<string, unknown>;
  buildConfiguration: Record<string, unknown>;
  autoDeploy?: boolean;
}) {
  if (
    !input.repository ||
    !input.branch ||
    !input.rootDirectory ||
    input.servicePort < 1 ||
    input.servicePort > 65535
  ) {
    throw new Error("Invalid deployment configuration input");
  }
  return {
    repository: input.repository,
    branch: input.branch,
    root_directory: input.rootDirectory,
    runtime: input.runtime,
    service_port: input.servicePort,
    install_configuration: input.installConfiguration,
    build_configuration: input.buildConfiguration,
    ...(input.autoDeploy === undefined ? {} : { auto_deploy: input.autoDeploy }),
  };
}

export function serviceCanDeploy(state: ServiceLifecycle) {
  return state === "managed";
}

export function serviceLifecycleLabel(state: ServiceLifecycle) {
  return {
    adopted: "Adopted · Unmanaged",
    configured: "Configured · Unmanaged",
    managed: "Managed",
  }[state];
}

export function availableInventoryUnits<T extends { unit_name: string }>(
  inventory: T[],
  boundUnitNames: string[],
): T[] {
  const bound = new Set(boundUnitNames);
  return inventory.filter((item) => !bound.has(item.unit_name));
}
