export const departmentSeedData = [
  {
    slug: "seo",
    name: "SEO",
    mission: "Build measurable organic visibility, qualified demand, conversion and revenue through a repeatable SEO operating system.",
  },
  {
    slug: "product-engineering",
    name: "Product Engineering",
    mission: "Deliver reusable, maintainable products through shared architecture, design patterns and engineering standards.",
  },
  {
    slug: "ai-automation",
    name: "AI & Automation",
    mission: "Design AI-native agents, workflows and automations that reduce operational effort while preserving human control for sensitive actions.",
  },
  {
    slug: "sales-client-success",
    name: "Sales & Client Success",
    mission: "Create qualified pipeline, productized proposals, consistent onboarding, retention and measurable client outcomes.",
  },
  {
    slug: "operations",
    name: "Operations",
    mission: "Run delivery governance, finance, QA, reliability and the agency operating cadence.",
  },
] as const;

export const seoRoleDefinitions = [
  {
    slug: "seo-director",
    name: "SEO Director",
    mission: "Own SEO strategy, priorities, business outcomes and final SEO decisions.",
    responsibilities: ["Strategy", "Prioritization", "KPI ownership", "Client decision support", "Quarterly planning"],
  },
  {
    slug: "seo-strategist",
    name: "SEO Strategist / Topical Authority",
    mission: "Translate search demand into intent-led pillar, cluster and landing-page architecture.",
    responsibilities: ["Search intent", "Keyword mapping", "Pillar/cluster architecture", "Cannibalization prevention", "Competitor gaps"],
  },
  {
    slug: "seo-data-analyst",
    name: "SEO Data Analyst",
    mission: "Turn GSC, analytics, ranking and lead data into prioritized evidence-backed actions.",
    responsibilities: ["GSC analysis", "Trend detection", "Opportunity scoring", "Attribution", "Forecasting"],
  },
  {
    slug: "content-strategist",
    name: "Content Strategist",
    mission: "Define content assets, briefs, refresh strategy and editorial quality around business intent.",
    responsibilities: ["Content briefs", "Create/refresh/merge decisions", "Entity coverage", "Editorial planning", "Freshness"],
  },
  {
    slug: "seo-editor",
    name: "SEO Content Editor",
    mission: "Prepare search-facing content for intent satisfaction, clarity, on-page quality and conversion.",
    responsibilities: ["On-page optimization", "Titles and headings", "Semantic coverage", "CTR improvements", "CTA alignment"],
  },
  {
    slug: "internal-linking",
    name: "Internal Linking Specialist",
    mission: "Improve authority flow, context and discoverability through a deliberate internal link graph.",
    responsibilities: ["Link graph", "Anchor strategy", "Orphan detection", "Contextual links", "Pillar support"],
  },
  {
    slug: "digital-pr",
    name: "Off-page & Digital PR Specialist",
    mission: "Build relevant external authority, mentions and link acquisition without compromising quality.",
    responsibilities: ["Backlink strategy", "Digital PR", "Link gap analysis", "Brand mentions", "Outreach planning"],
  },
  {
    slug: "technical-seo",
    name: "Technical SEO Specialist",
    mission: "Protect crawlability, rendering, indexability, canonical integrity and technical search performance.",
    responsibilities: ["Crawl/indexing", "Canonical/robots", "Sitemaps", "Schema", "Core Web Vitals", "Technical QA"],
  },
  {
    slug: "seo-automation-engineer",
    name: "SEO Automation Engineer",
    mission: "Connect search data, Agency decisions and execution tools into safe AI-assisted SEO workflows.",
    responsibilities: ["MCP workflows", "GSC automation", "WordPress automation", "Opportunity detection", "Monitoring"],
  },
  {
    slug: "seo-qa",
    name: "SEO QA",
    mission: "Verify SEO changes before and after publication and detect regressions early.",
    responsibilities: ["Pre-publish QA", "Post-publish QA", "Indexability checks", "Regression detection", "Evidence capture"],
  },
  {
    slug: "seo-project-manager",
    name: "SEO Project Manager",
    mission: "Turn strategy into constrained weekly outcomes with clear owners, priorities and evidence of completion.",
    responsibilities: ["Sprint planning", "Task ownership", "Dependencies", "Weekly review", "Client reporting"],
  },
  {
    slug: "cro-seo-ux",
    name: "CRO & SEO UX Specialist",
    mission: "Convert qualified organic demand into leads and revenue through landing-page UX and conversion improvements.",
    responsibilities: ["Conversion analysis", "CTA design", "Form UX", "Landing-page experiments", "Organic funnel optimization"],
  },
] as const;

export const seoKpiDefinitions = [
  { slug: "indexed-valid-pages", name: "Indexed / Valid Pages", unit: "pages", direction: "increase" as const },
  { slug: "organic-impressions", name: "Organic Impressions", unit: "count", direction: "increase" as const },
  { slug: "organic-clicks", name: "Organic Clicks", unit: "count", direction: "increase" as const },
  { slug: "organic-ctr", name: "Organic CTR", unit: "percent", direction: "increase" as const },
  { slug: "average-position", name: "Average Position", unit: "position", direction: "decrease" as const },
  { slug: "non-brand-organic-clicks", name: "Non-brand Organic Clicks", unit: "count", direction: "increase" as const },
  { slug: "organic-qualified-leads", name: "Qualified Organic Leads", unit: "leads", direction: "increase" as const },
  { slug: "organic-conversion-rate", name: "Organic Conversion Rate", unit: "percent", direction: "increase" as const },
  { slug: "organic-revenue", name: "Revenue from Organic", unit: "currency", direction: "increase" as const },
  { slug: "cost-per-organic-lead", name: "Cost per Organic Lead", unit: "currency", direction: "decrease" as const },
  { slug: "seo-client-retention", name: "SEO Client Retention", unit: "percent", direction: "increase" as const },
  { slug: "content-decay-pages", name: "Content Decay Pages", unit: "pages", direction: "decrease" as const },
  { slug: "topical-coverage", name: "Topical Coverage", unit: "percent", direction: "increase" as const },
] as const;
