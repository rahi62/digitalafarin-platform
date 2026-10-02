"use server";

import { redirect } from 'next/navigation';
import { revalidatePath } from 'next/cache';
import { ControlPlaneError, provisionService, retryProvisionService } from '@/lib/control-plane';
import { buildProvisionRequest, provisionError, serviceDetailPath } from '@/lib/provisioning';

export async function provisionAction(_previous: { error: string }, form: FormData): Promise<{ error: string }> {
  const value = (key: string) => String(form.get(key) ?? '').trim();
  const projectId = value('project_id');
  let target: string;
  try {
    const data = buildProvisionRequest({ name: value('name'), repository: value('repository'), branch: value('branch'),
      rootDirectory: value('root_directory'), servicePort: Number(value('service_port')), serverId: value('server_id'), healthPath: value('health_path') });
    const result = await provisionService(projectId, data, value('request_id'));
    target = serviceDetailPath(projectId, result.service_id);
  } catch (error) {
    if (error instanceof ControlPlaneError) return { error: provisionError(error.code) };
    if (error instanceof TypeError) return { error: 'آدرس مخزن یا اتصال به سرور معتبر نیست.' };
    return { error: error instanceof Error ? error.message : provisionError('unknown') };
  }
  revalidatePath(`/projects/${projectId}`);
  redirect(target);
}

export async function retryProvisionAction(_previous: { error: string }, form: FormData): Promise<{ error: string }> {
  const serviceId = String(form.get('service_id') ?? '');
  const projectId = String(form.get('project_id') ?? '');
  try {
    await retryProvisionService(serviceId, String(form.get('request_id') ?? ''));
  } catch (error) {
    return { error: provisionError(error instanceof ControlPlaneError ? error.code : 'unknown') };
  }
  revalidatePath(`/projects/${projectId}/services/${serviceId}`);
  return { error: '' };
}
