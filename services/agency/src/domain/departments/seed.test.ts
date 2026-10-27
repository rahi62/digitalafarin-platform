import { describe, expect, it } from "vitest";
import { departmentSeedData, seoKpiDefinitions, seoRoleDefinitions } from "./seed-data.js";
import { seoWorkflowDefinition } from "../workflows/seo.js";

describe("Agency department seed data", () => {
  it("defines the five v1 departments with unique slugs", () => {
    expect(departmentSeedData).toHaveLength(5);
    expect(new Set(departmentSeedData.map((item) => item.slug)).size).toBe(5);
    expect(departmentSeedData.map((item) => item.slug)).toEqual([
      "seo",
      "product-engineering",
      "ai-automation",
      "sales-client-success",
      "operations",
    ]);
  });

  it("defines the complete SEO virtual department role roster", () => {
    expect(seoRoleDefinitions).toHaveLength(12);
    expect(new Set(seoRoleDefinitions.map((item) => item.slug)).size).toBe(12);
    expect(seoRoleDefinitions.map((item) => item.slug)).toContain("seo-director");
    expect(seoRoleDefinitions.map((item) => item.slug)).toContain("technical-seo");
    expect(seoRoleDefinitions.map((item) => item.slug)).toContain("seo-automation-engineer");
    expect(seoRoleDefinitions.map((item) => item.slug)).toContain("seo-qa");
    expect(seoRoleDefinitions.map((item) => item.slug)).toContain("cro-seo-ux");
  });

  it("defines the SEO operating workflow in the approved order", () => {
    expect(seoWorkflowDefinition.slug).toBe("seo-operating-system-v1");
    expect(seoWorkflowDefinition.steps.map((step) => step.name)).toEqual([
      "Measure",
      "Diagnose",
      "Prioritize",
      "Plan",
      "Implement",
      "QA",
      "Validate",
      "Measure Impact",
      "Learn",
      "Refresh",
    ]);
  });

  it("defines unique business-aware SEO KPIs", () => {
    const slugs = seoKpiDefinitions.map((item) => item.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    expect(slugs).toContain("organic-qualified-leads");
    expect(slugs).toContain("organic-revenue");
    expect(slugs).toContain("organic-conversion-rate");
    expect(slugs).toContain("indexed-valid-pages");
    expect(slugs).toContain("content-decay-pages");
  });
});
