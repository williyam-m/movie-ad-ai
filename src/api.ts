import type { AnalysisJob, Brand, PolicyInput } from './types'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new Error(payload?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export async function fetchCatalogue(): Promise<Brand[]> {
  const response = await fetch('/api/catalogue')
  const payload = await parseResponse<{ items: Brand[] }>(response)
  return payload.items
}

export async function fetchHealth(): Promise<boolean> {
  try {
    const response = await fetch('/api/health')
    return response.ok
  } catch {
    return false
  }
}

export async function startDemo(policy: PolicyInput): Promise<AnalysisJob> {
  const response = await fetch('/api/demo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      max_breaks_per_hour: policy.maxBreaksPerHour,
      min_gap_seconds: policy.minGapSeconds,
      max_ad_load_percent: policy.maxAdLoadPercent,
    }),
  })
  return parseResponse<AnalysisJob>(response)
}

export async function uploadVideo(
  video: File,
  policy: PolicyInput,
  catalogue?: File,
): Promise<AnalysisJob> {
  const data = new FormData()
  data.append('video', video)
  data.append('max_breaks_per_hour', String(policy.maxBreaksPerHour))
  data.append('min_gap_seconds', String(policy.minGapSeconds))
  data.append('max_ad_load_percent', String(policy.maxAdLoadPercent))
  if (catalogue) data.append('catalogue', catalogue)

  const response = await fetch('/api/jobs', { method: 'POST', body: data })
  return parseResponse<AnalysisJob>(response)
}

export async function fetchJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetch(`/api/jobs/${jobId}`)
  return parseResponse<AnalysisJob>(response)
}