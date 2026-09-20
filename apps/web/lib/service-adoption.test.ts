import test from "node:test";
import assert from "node:assert/strict";
import {
  buildAdoptServiceRequest,
  buildDeploymentConfigurationRequest,
  serviceCanDeploy,
  serviceLifecycleLabel,
} from "./service-adoption.ts";

test("adoption builder emits only server unit and project-local name", () => {
  assert.deepEqual(
    buildAdoptServiceRequest("server-id", "oily-backend.service", "backend"),
    { server_id: "server-id", unit_name: "oily-backend.service", name: "backend" },
  );
});

test("configuration builder emits only deployment metadata", () => {
  assert.deepEqual(
    buildDeploymentConfigurationRequest({
      repository: "https://github.com/example/oily.git",
      branch: "main",
      rootDirectory: "backend",
      runtime: "python-django",
      servicePort: 8000,
      installConfiguration: { requirements_file: "requirements.txt" },
      buildConfiguration: { migrate: true, collectstatic: true, gunicorn_module: "config.wsgi:application" },
    }),
    {
      repository: "https://github.com/example/oily.git",
      branch: "main",
      root_directory: "backend",
      runtime: "python-django",
      service_port: 8000,
      install_configuration: { requirements_file: "requirements.txt" },
      build_configuration: { migrate: true, collectstatic: true, gunicorn_module: "config.wsgi:application" },
    },
  );
});

test("only managed services can render deploy controls", () => {
  assert.equal(serviceCanDeploy("adopted"), false);
  assert.equal(serviceCanDeploy("configured"), false);
  assert.equal(serviceCanDeploy("managed"), true);
  assert.equal(serviceLifecycleLabel("adopted"), "Adopted · Unmanaged");
  assert.equal(serviceLifecycleLabel("configured"), "Configured · Unmanaged");
  assert.equal(serviceLifecycleLabel("managed"), "Managed");
});

test("already bound inventory units are removed from adoption choices", async () => {
  const { availableInventoryUnits } = await import("./service-adoption.ts");
  assert.deepEqual(
    availableInventoryUnits(
      [{ unit_name: "a.service" }, { unit_name: "b.service" }],
      ["a.service"],
    ),
    [{ unit_name: "b.service" }],
  );
});
