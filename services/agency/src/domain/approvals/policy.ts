export type RiskLevel = "low" | "medium" | "high" | "critical";

const alwaysHumanActions = new Set([
  "redirect",
  "canonical",
  "noindex",
  "indexing_change",
  "delete",
  "unpublish",
  "mass_publish",
  "money_page_rewrite",
  "production_deploy",
  "dns_change",
  "server_change",
]);

export function evaluateApprovalRequirement(input: {
  riskLevel: RiskLevel;
  actionType: string;
  explicitApprovalRequired?: boolean;
  allowMediumRiskAutoApproval?: boolean;
}): boolean {
  if (input.riskLevel === "high" || input.riskLevel === "critical") return true;
  if (alwaysHumanActions.has(input.actionType)) return true;
  if (input.explicitApprovalRequired) return true;
  if (input.riskLevel === "medium") return !input.allowMediumRiskAutoApproval;
  return false;
}

export function isAlwaysHumanAction(actionType: string): boolean {
  return alwaysHumanActions.has(actionType);
}
