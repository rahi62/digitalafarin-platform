export function GscOAuthLink({ className, label }: { className: string; label: string }) {
  return <a className={className} href="/api/gsc/oauth/start">{label}</a>;
}
