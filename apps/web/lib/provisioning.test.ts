import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildProvisionRequest, provisionError, newServicePath, serviceDetailPath } from './provisioning.ts';

const input = { name: ' web ', repository: 'https://github.com/example/demo.git', branch: 'main', rootDirectory: '.', servicePort: 3000, serverId: '11111111-1111-4111-8111-111111111111', healthPath: '/' };
test('provisioning sends only validated logical configuration', () => {
  const data = buildProvisionRequest(input);
  assert.equal(data.name, 'web');
  assert.equal(data.runtime, 'node-nextjs');
  assert.equal(data.target_server_id, input.serverId);
  assert.equal('unit_name' in data, false);
  assert.equal('command' in data, false);
});
test('provisioning rejects missing fields and unsafe paths before submission', () => {
  for (const patch of [{ name: '' }, { rootDirectory: '../app' }, { repository: 'https://u:p@github.com/a/b' }, { servicePort: 80 }, { healthPath: '//outside.test' }, { serverId: '' }]) {
    assert.throws(() => buildProvisionRequest({ ...input, ...patch }));
  }
});
test('provisioning errors are actionable and do not echo server content', () => {
  assert.match(provisionError('port_conflict'), /پورت/);
  assert.equal(provisionError('unknown-secret'), provisionError('unknown'));
});

test('project Add Service and empty state use the dedicated service route', () => {
  assert.equal(newServicePath('a b'), '/projects/a%20b/services/new');
  const page = readFileSync(new URL('../app/projects/[projectId]/page.tsx', import.meta.url), 'utf8');
  assert.match(page, /No services yet/);
  assert.match(page, /newServicePath\(project\.id\)/);
  assert.doesNotMatch(page, /\/migration\?project=/);
});

test('new-service submission navigates to its project-scoped detail and keeps Migration advanced', () => {
  assert.equal(serviceDetailPath('a b', 'service/id'), '/projects/a%20b/services/service%2Fid');
  const action = readFileSync(new URL('../app/projects/[projectId]/services/new/actions.ts', import.meta.url), 'utf8');
  const nav = readFileSync(new URL('../components/SidebarNav.tsx', import.meta.url), 'utf8');
  assert.match(action, /serviceDetailPath\(projectId, result\.service_id\)/);
  assert.match(nav, /href: "\/migration", label: "Migration"/);
});

test('new service asks for a supported runtime and an explicit port', () => {
  const form = readFileSync(new URL('../app/projects/[projectId]/services/new/ProvisionForm.tsx', import.meta.url), 'utf8');
  assert.match(form, /name="runtime"/);
  assert.match(form, /node-nextjs/);
  assert.match(form, /name="service_port"[^>]*required/);
  assert.doesNotMatch(form, /name="service_port"[^>]*defaultValue/);
});
