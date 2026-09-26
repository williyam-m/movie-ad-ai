export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface Brand {
  id: string
  name: string
  category: string
  description: string
  tagline: string
  color: string
  target_activities: string[]
  positive_contexts: string[]
  negative_contexts: string[]
}

export interface Scene {
  id: string
  start: number
  end: number
  duration: number
  visual_score: number
  dominant_activity: string
  activities: string[]
  contexts: string[]
  mood: string
  description: string
  transcript: string
}

export interface CandidateFeatures {
  visual_change: number
  silence_seconds: number
  semantic_shift: number
  speech_overlap: boolean
  edge_margin: number
}

export interface BreakCandidate {
  id: string
  timestamp: number
  interruptibility_score: number
  is_safe: boolean
  decision: string
  reasons: string[]
  features: CandidateFeatures
}

export interface MatchedBrand {
  id: string
  name: string
  category: string
  tagline: string
  color: string
}

export interface BreakSlot {
  id: string
  timestamp: number
  time_offset: string
  score: number
  scene_id: string
  brand: MatchedBrand
  creative_url: string
  duration: number
  match_score: number
  why: string[]
  blocked_brands: string[]
}

export interface AnalysisPolicy {
  max_breaks_per_hour: number
  min_gap_seconds: number
  max_ad_load_percent: number
  min_interruptibility: number
}

export interface AnalysisSummary {
  scene_count: number
  candidate_count: number
  safe_candidate_count: number
  break_count: number
  ad_load_percent: number
}

export interface ModelReport {
  visual: string
  speech: string
  semantics: string
  degraded: boolean
  notes: string[]
}

export interface AnalysisResult {
  job_id: string
  source_name: string
  duration_seconds: number
  media_url: string
  generated_at: string
  summary: AnalysisSummary
  policy: AnalysisPolicy
  models: ModelReport
  scenes: Scene[]
  candidates: BreakCandidate[]
  breaks: BreakSlot[]
  manifest_url: string
  debug_url: string
}

export interface AnalysisJob {
  id: string
  status: JobStatus
  stage: string
  progress: number
  error: string | null
  result: AnalysisResult | null
}

export interface PolicyInput {
  maxBreaksPerHour: number
  minGapSeconds: number
  maxAdLoadPercent: number
}