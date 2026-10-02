export type ProvisionInput = {
  name: string; repository: string; branch: string; rootDirectory: string;
  servicePort: number; serverId: string; healthPath: string;
};

export function newServicePath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/services/new`;
}

export function serviceDetailPath(projectId: string, serviceId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/services/${encodeURIComponent(serviceId)}`;
}

export function buildProvisionRequest(input: ProvisionInput) {
  const name = input.name.trim();
  const repository = input.repository.trim();
  const branch = input.branch.trim();
  const root = input.rootDirectory.trim();
  const health = input.healthPath.trim();
  const repo = new URL(repository);
  if (!/^[a-z0-9][a-z0-9_-]{0,79}$/.test(name)) throw new Error('نام سرویس باید با حروف کوچک انگلیسی و بدون فاصله باشد.');
  if (repo.protocol !== 'https:' || !['github.com', 'gitlab.com', 'bitbucket.org'].includes(repo.hostname) || repo.username || repo.password || repo.port || repo.search || repo.hash || !/^\/[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)+$/.test(repo.pathname)) throw new Error('آدرس HTTPS مخزن عمومی GitHub، GitLab یا Bitbucket را وارد کنید.');
  if (!/^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$/.test(branch) || branch.includes('..') || branch.includes('//') || /(?:\/|\.|\.lock)$/.test(branch)) throw new Error('نام branch معتبر نیست.');
  if (root !== '.' && (!/^[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*$/.test(root) || root.split('/').some(x => x === '.' || x === '..'))) throw new Error('مسیر پروژه باید داخل مخزن باشد؛ برای ریشه از نقطه استفاده کنید.');
  if (!Number.isInteger(input.servicePort) || input.servicePort < 1024 || input.servicePort > 65535) throw new Error('پورت باید بین ۱۰۲۴ تا ۶۵۵۳۵ باشد.');
  if (!/^[0-9a-f-]{36}$/i.test(input.serverId)) throw new Error('یک سرور آماده انتخاب کنید.');
  if (!/^\/(?:[A-Za-z0-9_.~-]+\/?)*$/.test(health)) throw new Error('مسیر health باید با یک / شروع شود.');
  return { name, repository, branch, root_directory: root, runtime: 'node-nextjs' as const,
    service_port: input.servicePort, target_server_id: input.serverId, health_path: health,
    install_configuration: { package_manager: 'npm', lockfile: 'package-lock.json' },
    build_configuration: { build_script: 'build' } };
}

export function provisionError(code: string): string {
  const messages: Record<string, string> = {
    port_conflict: 'این پورت قبلاً به سرویس دیگری اختصاص داده شده است. پورت دیگری انتخاب کنید.',
    duplicate_service: 'نام این سرویس در پروژه وجود دارد. نام دیگری انتخاب کنید.',
    provisioning_unavailable: 'این سرور هنوز آمادهٔ ساخت سرویس نیست. Agent و helper را بروزرسانی کنید.',
    deployment_blocked: 'سرور آماده نیست یا فضای دیسک کافی ندارد. وضعیت سرور را بررسی کنید.',
    idempotency_conflict: 'این درخواست قبلاً با تنظیمات دیگری ثبت شده است. صفحه را تازه کنید.',
  };
  return messages[code] ?? 'ثبت درخواست انجام نشد. اتصال و تنظیمات را بررسی و دوباره تلاش کنید.';
}

export function lifecycleLabel(state: string): string {
  return ({ pending: 'در صف ساخت', provisioning: 'در حال ساخت', provision_failed: 'ساخت ناموفق', managed: 'مدیریت‌شده', adopted: 'شناسایی‌شده', configured: 'آمادهٔ انتقال' } as Record<string, string>)[state] ?? state;
}
