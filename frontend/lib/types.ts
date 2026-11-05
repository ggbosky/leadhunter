export type Segment = { key: string; label: string; tier: number; economic_base: number; visual_importance: number; typical_service: string };
export type Region = { code: string; name: string; country: string; cities: string[]; default_priority: number };

export type Meta = {
  segments: Segment[];
  tiers: Record<string, string>;
  regions: Region[];
  strategies: Record<string, string>;
  message_types: Record<string, string>;
  statuses: Record<string, string>;
  categories: Record<string, string>;
  disqualification_reasons: Record<string, string>;
  services: Record<string, string>;
  signal_types: Record<string, string>;
  suppression_reasons: Record<string, string>;
  job_types: Record<string, string>;
};

export type Shot = { url: string; full_url?: string; device: string };

export type LeadSummary = {
  id: number;
  name: string;
  segment_key: string | null;
  segment_label: string | null;
  tier: number | null;
  city: string | null;
  region_code: string | null;
  region_name: string | null;
  country: string;
  website_url: string | null;
  domain: string | null;
  status: string;
  disqualified_reason: string | null;
  ico: string | null;
  opportunity_score: number | null;
  confidence_score: number | null;
  category: string | null;
  category_label: string | null;
  design_gap: number | null;
  commercial_potential: number | null;
  buying_readiness: number | null;
  website_quality: number | null;
  website_quality_basis: string | null;
  outreach_reason: string | null;
  last_analyzed_at: string | null;
  first_seen_at: string;
  times_seen: number;
  hero_screenshot?: Shot | null;
  has_messages?: boolean;
  contact_name?: string | null;
  has_linkedin?: boolean;
};

export type Factor = { label: string; value: number | null; weight: number; evidence: string; known: boolean };
export type ScoreComponent = {
  key: string;
  label: string;
  score: number | null;
  confidence: number;
  reasons: string[];
  factors: Factor[];
  note: string | null;
};

export type Score = {
  opportunity_score: number | null;
  confidence_score: number | null;
  category: string | null;
  category_label: string | null;
  design_gap: number | null;
  commercial_potential: number | null;
  buying_readiness: number | null;
  service_fit: number | null;
  contactability: number | null;
  business_quality: number | null;
  website_quality: number | null;
  website_quality_basis: string | null;
  components: Record<string, ScoreComponent> & { weights?: Record<string, number>; known_weight_share?: number };
  recommended_service: string | null;
  estimated_budget: { service: string; label: string; min: number | null; max: number | null; note: string } | null;
  outreach_reason: string | null;
  disqualification_reasons: { code: string; label: string; detail: string }[];
  computed_at: string;
  algorithm_version: string;
};

export type Contact = {
  id: number;
  company_id: number;
  name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  is_decision_maker: boolean;
  is_primary: boolean;
  verified: boolean;
  source: string;
  source_evidence: string | null;
  connection_status: string;
  first_contacted_at: string | null;
  last_contacted_at: string | null;
  replied_at: string | null;
  contact_attempts: number;
  next_step: string | null;
  next_step_at: string | null;
  do_not_contact: boolean;
  notes: string | null;
};

export type Message = {
  id: number;
  company_id: number;
  contact_id: number | null;
  strategy: string;
  strategy_label: string;
  message_type: string;
  message_type_label: string;
  content: string;
  facts_used: { key: string; text: string; source: string }[];
  generator: string;
  quality_warnings: string[];
  status: string;
  sent_at: string | null;
  outcome: string;
  created_at: string;
  chars: number;
};

export type Criterion = {
  key: string;
  label: string;
  score: number | null;
  observation: string;
  evidence: string;
  recommendation: string;
  confidence: number;
  weight: number;
};

export type Task = {
  id: number;
  company_id: number;
  contact_id: number | null;
  task_type: string;
  title: string;
  due_at: string;
  status: string;
  sequence_number: number;
  reason: string | null;
  completed_at: string | null;
  cancelled_reason: string | null;
  overdue: boolean;
  company_name?: string;
  contact_name?: string | null;
  linkedin_url?: string | null;
};

export type Issue = { code: string; title: string; detail: string; severity: string; penalty: number };

export type CompanyDetail = LeadSummary & {
  legal_name: string | null;
  legal_form: string | null;
  founded_on: string | null;
  registry_status: string | null;
  registered_capital: number | null;
  nace_codes: string[];
  street: string | null;
  postcode: string | null;
  phone: string | null;
  email: string | null;
  social_links: Record<string, string>;
  opening_hours: string | null;
  notes: string | null;
  sources: { source: string; key: string; external_id: string; url: string | null; fetched_at: string }[];
  website: {
    url: string;
    final_url: string | null;
    reachable: boolean | null;
    status_code: number | null;
    robots_allowed: boolean | null;
    https: boolean | null;
    cms: string | null;
    technologies: string[];
    title: string | null;
    meta_description: string | null;
    discovered_pages: Record<string, string>;
    last_crawled_at: string | null;
    last_error: string | null;
    facts: Record<string, unknown>;
  } | null;
  audit: {
    id: number;
    technical_score: number | null;
    issues: Issue[];
    complete: boolean;
    incomplete_reasons: string[];
    metrics: Record<string, unknown>;
    created_at: string;
    screenshots: { page: string; device: string; url: string; fold_url: string | null; path: string }[];
  } | null;
  visual: {
    id: number;
    status: string;
    provider: string;
    model: string | null;
    visual_score: number | null;
    confidence: number | null;
    criteria: Criterion[];
    summary: string | null;
    strengths: string[];
    top_issues: string[];
    error: string | null;
    is_expert_estimate: boolean;
    design_era: string | null;
    business_impression: string | null;
    created_at: string;
  } | null;
  signals: { id: number; signal_type: string; category: string; description: string; evidence: string | null; source_url: string | null; strength: number; detected_at: string }[];
  score: Score | null;
  score_history: { opportunity_score: number | null; confidence_score: number | null; category: string | null; computed_at: string }[];
  contacts: Contact[];
  best_contact_id: number | null;
  linkedin: { links: { label: string; url: string; kind: string }[]; queries: string[] };
  messages: Message[];
  events: { id: number; event_type: string; strategy: string | null; occurred_at: string; notes: string | null; contact_id: number | null }[];
  tasks: Task[];
};

export type Job = {
  id: number;
  job_type: string;
  label: string;
  payload: Record<string, unknown>;
  status: string;
  priority: number;
  attempts: number;
  max_attempts: number;
  trigger: string;
  parent_id: number | null;
  run_after: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  last_error: string | null;
  log: { t: string; m: string }[];
};
