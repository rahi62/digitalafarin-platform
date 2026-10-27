export const seoWorkflowDefinition = {
  slug: "seo-operating-system-v1",
  name: "SEO Operating System v1",
  description: "Repeatable SEO delivery loop from measurement and diagnosis through implementation, QA, validation and refresh.",
  status: "active" as const,
  steps: [
    {
      position: 1,
      name: "Measure",
      stepType: "analysis" as const,
      config: { outcome: "Establish current technical, visibility, traffic, lead and revenue baseline." },
    },
    {
      position: 2,
      name: "Diagnose",
      stepType: "analysis" as const,
      config: { outcome: "Identify technical issues, content gaps, decay, cannibalization and conversion constraints." },
    },
    {
      position: 3,
      name: "Prioritize",
      stepType: "analysis" as const,
      config: { outcome: "Rank incidents and opportunities by business impact, evidence, effort, urgency and risk." },
    },
    {
      position: 4,
      name: "Plan",
      stepType: "manual" as const,
      config: { outcome: "Create a constrained SEO sprint with owners, expected impact, dependencies and Definition of Done." },
    },
    {
      position: 5,
      name: "Implement",
      stepType: "execution" as const,
      config: { outcome: "Apply approved content, internal-link, technical or CRO changes through the correct executor." },
    },
    {
      position: 6,
      name: "QA",
      stepType: "qa" as const,
      config: { outcome: "Verify content, rendered output, metadata, links, indexability, mobile UX and tracking." },
    },
    {
      position: 7,
      name: "Validate",
      stepType: "qa" as const,
      config: { outcome: "Confirm crawl/index state and ensure no technical or content regression was introduced." },
    },
    {
      position: 8,
      name: "Measure Impact",
      stepType: "analysis" as const,
      config: { outcome: "Measure impressions, clicks, rankings, leads, conversion and revenue movement after change." },
    },
    {
      position: 9,
      name: "Learn",
      stepType: "analysis" as const,
      config: { outcome: "Record evidence, decision rationale, unexpected effects and reusable learnings in Agency memory." },
    },
    {
      position: 10,
      name: "Refresh",
      stepType: "manual" as const,
      config: { outcome: "Schedule the next refresh, expansion, consolidation or monitoring action based on results." },
    },
  ],
} as const;
