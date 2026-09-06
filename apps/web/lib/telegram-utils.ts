const TELEGRAM_ALIAS_RE = /^[a-z0-9][a-z0-9_-]{0,79}$/;

export function normalizeTelegramAlias(value: string): string {
  return value.trim().toLowerCase();
}

export function validateTelegramAlias(value: string): boolean {
  return TELEGRAM_ALIAS_RE.test(normalizeTelegramAlias(value));
}
