import type { AnalysisJob, Brand, PolicyInput } from './types'
import catalogueData from '../../data/brands.json'
import { DEMO_RESULT } from './demoResult'

export const MAX_UPLOAD_BYTES = 400 * 1024 * 1024
export const STATIC_MODE = import.meta.env.VITE_STATIC_SPACE === 'true'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new Error(payload?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

function dataUrl(type: string, content: string): string {
  return `data:${type};charset=utf-8,${encodeURIComponent(content)}`
}

export async function fetchCatalogue(): Promise<Brand[]> {
  if (STATIC_MODE) return catalogueData.brands
  const response = await fetch('/api/catalogue')
  const payload = await parseResponse<{ items: Brand[] }>(response)
  return payload.items
}

export async function fetchHealth(): Promise<boolean> {
  if (STATIC_MODE) return true
  try {
    const response = await fetch('/api/health')
    return response.ok
  } catch {
    return false
  }
}

export async function startDemo(policy: PolicyInput): Promise<AnalysisJob> {
  if (!STATIC_MODE) {
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

  await new Promise((resolve) => window.setTimeout(resolve, 350))
  const result = structuredClone(DEMO_RESULT)
  result.policy.max_breaks_per_hour = policy.maxBreaksPerHour
  result.policy.min_gap_seconds = policy.minGapSeconds
  result.policy.max_ad_load_percent = policy.maxAdLoadPercent

  const adLoad = result.summary.ad_load_percent
  if (policy.maxAdLoadPercent < adLoad) {
    result.breaks = []
    result.summary.break_count = 0
    result.summary.ad_load_percent = 0
  }

  const origin = window.location.origin
  const creativeUrl = `${origin}${result.breaks[0]?.creative_url ?? ''}`
  const adBreak = result.breaks.length === 0 ? '' : `<vmap:AdBreak timeOffset="00:00:28.021" breakType="linear" breakId="break-01"><vmap:AdSource id="source-break-01" allowMultipleAds="false" followRedirects="true"><vmap:VASTAdData><VAST version="4.2"><Ad id="ad-break-01"><InLine><AdSystem version="1.0">Movie Ad AI</AdSystem><AdTitle>RannaBondhu</AdTitle><Impression>${origin}</Impression><Creatives><Creative><Linear><Duration>00:00:06.000</Duration><MediaFiles><MediaFile delivery="progressive" type="video/mp4" width="960" height="540">${creativeUrl}</MediaFile></MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST></vmap:VASTAdData></vmap:AdSource></vmap:AdBreak>`
  const vmap = `<?xml version="1.0" encoding="UTF-8"?>\n<vmap:VMAP xmlns:vmap="http://www.iab.net/videosuite/vmap" version="1.0">${adBreak}</vmap:VMAP>`
  result.manifest_url = dataUrl('application/xml', vmap)
  result.debug_url = dataUrl('application/json', JSON.stringify(result, null, 2))

  return {
    id: result.job_id,
    status: 'completed',
    stage: 'Verified analysis loaded',
    progress: 1,
    error: null,
    result,
  }
}

export async function uploadVideo(
  video: File,
  policy: PolicyInput,
  catalogue?: File,
): Promise<AnalysisJob> {
  if (STATIC_MODE) throw new Error('Video uploads require the Docker deployment')
  if (video.size > MAX_UPLOAD_BYTES) {
    throw new Error('Video exceeds the 400 MB upload limit')
  }
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
  if (STATIC_MODE) {
    if (jobId !== DEMO_RESULT.job_id) throw new Error('Analysis job not found')
    return startDemo({
      maxBreaksPerHour: DEMO_RESULT.policy.max_breaks_per_hour,
      minGapSeconds: DEMO_RESULT.policy.min_gap_seconds,
      maxAdLoadPercent: DEMO_RESULT.policy.max_ad_load_percent,
    })
  }
  const response = await fetch(`/api/jobs/${jobId}`)
  return parseResponse<AnalysisJob>(response)
}