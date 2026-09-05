import type { HTMLAttributes } from "react";

export function LtrText({ className = "", ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span dir="ltr" className={`ltr-island ${className}`.trim()} {...props} />;
}
