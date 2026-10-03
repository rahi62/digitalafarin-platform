"use client";

import { useActionState } from "react";
import {
  deleteProjectAction,
  removeServiceAction,
  updateProjectSettingsAction,
  updateServiceSettingsAction,
  type SettingsActionState,
} from "@/app/projects/settings-actions";
import type { Project, ProjectService } from "@/lib/control-plane";

const initialState: SettingsActionState = {};

function Feedback({ state }: { state: SettingsActionState }) {
  if (state.error) return <p className="railFormError" role="alert">{state.error}</p>;
  if (state.success) return <p className="railFormSuccess" role="status">{state.success}</p>;
  return null;
}

export function ProjectSettingsForm({ project }: { project: Project }) {
  const [updateState, updateAction, updatePending] = useActionState(updateProjectSettingsAction, initialState);
  const [deleteState, deleteAction, deletePending] = useActionState(deleteProjectAction, initialState);

  return (
    <>
      <section className="railServiceSection">
        <div className="railSectionHeader">
          <div><h2>General</h2><p>نام و شناسه خوانای پروژه در Control Plane</p></div>
        </div>
        <form action={updateAction} className="railSettingsForm">
          <input type="hidden" name="project_id" value={project.id} />
          <label><span>Name</span><input name="name" defaultValue={project.name} required maxLength={120} /></label>
          <label><span>Slug</span><input name="slug" defaultValue={project.slug} required maxLength={80} dir="ltr" /></label>
          <Feedback state={updateState} />
          <button className="railPrimaryButton" type="submit" disabled={updatePending}>{updatePending ? "Saving…" : "Save changes"}</button>
        </form>
      </section>

      <section className="railServiceSection railDangerZone">
        <div className="railSectionHeader">
          <div><h2>Danger Zone</h2><p>حذف فقط برای پروژه خالی مجاز است؛ منابع متصل باعث مسدود شدن عملیات می‌شوند.</p></div>
        </div>
        <div className="railDangerSummary">
          <strong>{project.name}</strong>
          <code dir="ltr">{project.slug}</code>
          <span>{project.services?.length ?? 0} services · {project.variables?.length ?? 0} variables · {project.volumes?.length ?? 0} volumes · {project.databases?.length ?? 0} databases · {project.domains?.length ?? 0} domains</span>
        </div>
        <form action={deleteAction} className="railSettingsForm">
          <input type="hidden" name="project_id" value={project.id} />
          <label><span>برای تأیید، slug پروژه را وارد کنید: <code dir="ltr">{project.slug}</code></span><input name="confirmation" required autoComplete="off" dir="ltr" /></label>
          <Feedback state={deleteState} />
          <button className="railDangerButton" type="submit" disabled={deletePending}>{deletePending ? "Deleting…" : "Delete empty project"}</button>
        </form>
      </section>
    </>
  );
}

export function ServiceSettingsForm({ project, service }: { project: Project; service: ProjectService }) {
  const [updateState, updateAction, updatePending] = useActionState(updateServiceSettingsAction, initialState);
  const [removeState, removeAction, removePending] = useActionState(removeServiceAction, initialState);

  return (
    <>
      <section className="railServiceSection">
        <div className="railSectionHeader">
          <div><h2>Deployment configuration</h2><p>این تغییرات metadata/configuration پلتفرم را ویرایش می‌کنند و مستقیماً systemd را تغییر نمی‌دهند.</p></div>
        </div>
        <form action={updateAction} className="railSettingsForm">
          <input type="hidden" name="project_id" value={project.id} />
          <input type="hidden" name="service_id" value={service.id} />
          <label className="railFieldWide"><span>Repository</span><input name="repository" defaultValue={service.repository ?? ""} required dir="ltr" /></label>
          <label><span>Branch</span><input name="branch" defaultValue={service.branch ?? ""} required dir="ltr" /></label>
          <label><span>Root directory</span><input name="root_directory" defaultValue={service.root_directory ?? "."} required dir="ltr" /></label>
          <label><span>Runtime</span><select name="runtime" defaultValue={service.runtime ?? "node-nextjs"}><option value="node-nextjs">Node / Next.js</option><option value="python-django">Python / Django</option></select></label>
          <label><span>Port</span><input name="service_port" type="number" min={1} max={65535} defaultValue={service.service_port ?? ""} required dir="ltr" /></label>
          <label className="railFieldWide"><span>Install configuration (JSON)</span><textarea name="install_configuration" defaultValue={JSON.stringify(service.install_configuration ?? {}, null, 2)} rows={5} dir="ltr" /></label>
          <label className="railFieldWide"><span>Build configuration (JSON)</span><textarea name="build_configuration" defaultValue={JSON.stringify(service.build_configuration ?? {}, null, 2)} rows={5} dir="ltr" /></label>
          <Feedback state={updateState} />
          <button className="railPrimaryButton" type="submit" disabled={updatePending}>{updatePending ? "Saving…" : "Save configuration"}</button>
        </form>
      </section>

      <section className="railServiceSection railDangerZone">
        <div className="railSectionHeader">
          <div><h2>Danger Zone</h2><p>Remove from Platform فقط رکورد مدیریتی را حذف می‌کند؛ systemd، فایل‌های برنامه و VPS را حذف یا متوقف نمی‌کند.</p></div>
        </div>
        <div className="railDangerSummary">
          <strong>{service.name}</strong>
          <code dir="ltr">{service.unit_name}</code>
          <span>Lifecycle: {service.lifecycle_state} · Inventory: {service.inventory_status} · Server: {service.target_server_id}</span>
          {service.protected && <span className="railFormError">This service is protected and cannot be removed.</span>}
        </div>
        {!service.protected && (
          <form action={removeAction} className="railSettingsForm">
            <input type="hidden" name="project_id" value={project.id} />
            <input type="hidden" name="service_id" value={service.id} />
            <label><span>برای تأیید، نام unit را وارد کنید: <code dir="ltr">{service.unit_name}</code></span><input name="confirmation" required autoComplete="off" dir="ltr" /></label>
            <Feedback state={removeState} />
            <button className="railDangerButton" type="submit" disabled={removePending}>{removePending ? "Removing…" : "Remove from Platform"}</button>
          </form>
        )}
      </section>
    </>
  );
}
