import { describe, expect, it } from "vitest";
import { evaluateApprovalRequirement } from "./policy.js";

describe("Agency approval policy", () => {
  it("allows low-risk work without approval by default", () => {
    expect(evaluateApprovalRequirement({ riskLevel: "low", actionType: "content_analysis" })).toBe(false);
  });

  it("requires approval for medium risk unless policy explicitly allows automation", () => {
    expect(evaluateApprovalRequirement({ riskLevel: "medium", actionType: "content_update" })).toBe(true);
    expect(evaluateApprovalRequirement({ riskLevel: "medium", actionType: "content_update", allowMediumRiskAutoApproval: true })).toBe(false);
  });

  it("never allows high or critical risk to bypass human approval", () => {
    expect(evaluateApprovalRequirement({ riskLevel: "high", actionType: "content_update", allowMediumRiskAutoApproval: true })).toBe(true);
    expect(evaluateApprovalRequirement({ riskLevel: "critical", actionType: "content_update", allowMediumRiskAutoApproval: true })).toBe(true);
  });

  it("requires approval for protected production actions even when risk was misclassified low", () => {
    for (const actionType of ["redirect", "canonical", "noindex", "delete", "production_deploy", "dns_change"]) {
      expect(evaluateApprovalRequirement({ riskLevel: "low", actionType })).toBe(true);
    }
  });
});
