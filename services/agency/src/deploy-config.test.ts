import fs from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = process.cwd();

async function read(relativePath: string) {
  return fs.readFile(path.join(root, relativePath), "utf8");
}

describe("Agency Control Center deployment contract", () => {
  it("runs the admin as deploy on localhost port 3061", async () => {
    const service = await read("deploy/digitalafarin-agency-admin.service");
    const adminPackage = await read("admin/package.json");
    expect(service).toContain("User=deploy");
    expect(service).toContain("WorkingDirectory=/var/www/digitalafarin-agency-mcp/admin");
    expect(service).toContain("ExecStart=/usr/bin/npm run start");
    expect(service).toContain("ReadWritePaths=/var/www/digitalafarin-agency-mcp/admin/.next/cache");
    expect(adminPackage).toContain("next dev -H 127.0.0.1 -p 3061");
    expect(adminPackage).toContain("next start -H 127.0.0.1 -p 3061");
  });

  it("keeps MCP private while routing admin and REST API", async () => {
    const nginx = await read("deploy/nginx-agency-control-center.conf.example");
    expect(nginx).toContain("server_name agency.digitalafarin.ir");
    expect(nginx).toContain("location ^~ /mcp");
    expect(nginx).toContain("return 404");
    expect(nginx).toContain("proxy_pass http://127.0.0.1:3050");
    expect(nginx).toContain("proxy_pass http://127.0.0.1:3061");
  });

  it("installer verifies the admin before enabling it", async () => {
    const installer = await read("deploy/install-admin.sh");
    expect(installer).toContain("npm run check");
    expect(installer).toContain("npm run check:rtl");
    expect(installer).toContain("npm run test:rtl");
    expect(installer).toContain("npm run build");
    expect(installer).toContain("http://127.0.0.1:3061/login");
  });

  it("creates a safe JSON-first production env template for new installs", async () => {
    const installer = await read("deploy/install-server.sh");
    expect(installer).toContain("STORE_DRIVER=json");
    expect(installer).toContain("DATABASE_URL=postgresql://");
    expect(installer).toContain("ADMIN_ORIGIN=https://agency.digitalafarin.ir");
    expect(installer).toContain("SESSION_COOKIE_NAME=digitalafarin_agency_session");
    expect(installer).toContain("CSRF_SECRET=");
  });

  it("does not switch persistence until PostgreSQL import verification succeeds", async () => {
    const rollout = await read("deploy/rollout-postgres.sh");
    const backup = rollout.indexOf("cp --");
    const migrate = rollout.indexOf("run db:migrate");
    const imported = rollout.indexOf("run store:import");
    const verified = rollout.indexOf("run store:verify");
    const switched = rollout.indexOf("STORE_DRIVER=postgres");

    expect(backup).toBeGreaterThan(-1);
    expect(migrate).toBeGreaterThan(backup);
    expect(imported).toBeGreaterThan(migrate);
    expect(verified).toBeGreaterThan(imported);
    expect(switched).toBeGreaterThan(verified);
    expect(rollout).toContain('SERVICE="digitalafarin-agency-mcp.service"');
    expect(rollout).toContain('systemctl restart "$SERVICE"');
  });

  it("runs database migration/import commands as the deploy user", async () => {
    const rollout = await read("deploy/rollout-postgres.sh");
    expect(rollout).toContain('sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run db:migrate');
    expect(rollout).toContain('sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run db:seed');
    expect(rollout).toContain('sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run store:import -- "$DATA_FILE"');
    expect(rollout).toContain('sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run store:verify -- "$DATA_FILE"');
  });

  it("provides a production acceptance script without exposing MCP publicly", async () => {
    const verify = await read("deploy/verify-production.sh");
    expect(verify).toContain("http://127.0.0.1:3050/health");
    expect(verify).toContain("http://127.0.0.1:3030/health");
    expect(verify).toContain("http://127.0.0.1:3061/login");
    expect(verify).toContain('PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-https://agency.digitalafarin.ir}"');
    expect(verify).toContain('"$PUBLIC_ORIGIN/mcp"');
    expect(verify).toContain('[[ "$MCP_PUBLIC_STATUS" == "404" ]]');
  });

  it("documents backup, restore, rollback and WordPress regression procedures", async () => {
    const runbook = await read("docs/operations/agency-control-center-runbook.md");
    expect(runbook).toContain("PostgreSQL backup");
    expect(runbook).toContain("Restore drill");
    expect(runbook).toContain("Rollback to JSON");
    expect(runbook).toContain("WordPress MCP regression");
    expect(runbook).toContain("BOOTSTRAP_ADMIN_PASSWORD");
  });
});
