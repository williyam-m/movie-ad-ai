import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import {
  Activity,
  AlertTriangle,
  Check,
  ChevronRight,
  Clock3,
  Download,
  FileJson,
  Film,
  Gauge,
  LoaderCircle,
  Play,
  ShieldCheck,
  Sparkles,
  Upload,
} from 'lucide-react'
import {
  fetchCatalogue,
  fetchHealth,
  fetchJob,
  MAX_UPLOAD_BYTES,
  STATIC_MODE,
  startDemo,
  uploadVideo,
} from './api'
import { AdPlayer } from './components/AdPlayer'
import { PipelineExplainer } from './components/PipelineExplainer'
import type { AnalysisJob, Brand, PolicyInput } from './types'
import './App.css'

type InsightTab = 'breaks' | 'scenes' | 'safety' | 'catalogue'

const DEFAULT_POLICY: PolicyInput = {
  maxBreaksPerHour: 4,
  minGapSeconds: 420,
  maxAdLoadPercent: 8,
}

function formatTime(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  const remainder = value % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`
}

function scoreLabel(score: number): string {
  if (score >= 0.8) return 'Excellent'
  if (score >= 0.68) return 'Strong'
  return 'Acceptable'
}

function App() {
  const videoInput = useRef<HTMLInputElement>(null)
  const catalogueInput = useRef<HTMLInputElement>(null)
  const [selectedVideo, setSelectedVideo] = useState<File | null>(null)
  const [selectedCatalogue, setSelectedCatalogue] = useState<File | null>(null)
  const [catalogue, setCatalogue] = useState<Brand[]>([])
  const [policy, setPolicy] = useState<PolicyInput>(DEFAULT_POLICY)
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [activeTab, setActiveTab] = useState<InsightTab>('breaks')
  const [playhead, setPlayhead] = useState(0)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const jobId = job?.id
  const jobStatus = job?.status

  useEffect(() => {
    void fetchHealth().then(setApiOnline)
    void fetchCatalogue().then(setCatalogue).catch(() => setCatalogue([]))
  }, [])

  useEffect(() => {
    if (!jobId || (jobStatus !== 'queued' && jobStatus !== 'running')) return
    let cancelled = false
    let timer: number

    const poll = async () => {
      try {
        const nextJob = await fetchJob(jobId)
        if (!cancelled) {
          setJob(nextJob)
          if (nextJob.status === 'failed') setError(nextJob.error ?? 'Analysis failed')
          if (nextJob.status === 'queued' || nextJob.status === 'running') {
            timer = window.setTimeout(poll, nextJob.status === 'queued' ? 2200 : 1600)
          }
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : 'Status request failed')
        }
      }
    }

    timer = window.setTimeout(poll, 800)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [jobId, jobStatus])

  const selectVideo = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null
    if (file && file.size > MAX_UPLOAD_BYTES) {
      setSelectedVideo(null)
      setError('Video exceeds the 400 MB upload limit')
      event.target.value = ''
      return
    }
    setError(null)
    setSelectedVideo(file)
  }

  const runDemo = async () => {
    setError(null)
    setPlayhead(0)
    setIsSubmitting(true)
    try {
      setJob(await startDemo(policy))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to start demo')
    } finally {
      setIsSubmitting(false)
    }
  }

  const analyseUpload = async () => {
    if (!selectedVideo) {
      videoInput.current?.click()
      return
    }
    setError(null)
    setPlayhead(0)
    setIsSubmitting(true)
    try {
      setJob(await uploadVideo(selectedVideo, policy, selectedCatalogue ?? undefined))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Upload failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  const result = job?.result
  const isBusy = isSubmitting || job?.status === 'queued' || job?.status === 'running'
  const progress = job?.progress ?? 0

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="wordmark" aria-label="Movie Ad AI">
          <span>MOVIE</span>
          <i>AD AI</i>
        </div>
        <div className="product-name">
          <Film size={17} aria-hidden="true" />
          <strong>CONTEXT ENGINE</strong>
          <span>Contextual ad intelligence</span>
        </div>
        <div className={`service-state ${apiOnline ? 'online' : ''}`}>
          <span />
          {STATIC_MODE ? 'Verified demo' : apiOnline === null ? 'Checking API' : apiOnline ? 'System ready' : 'API offline'}
        </div>
      </header>

      <main>
        <section className="workspace-heading">
          <div>
            <p className="eyebrow">VIDEO UNDERSTANDING / ADTECH</p>
            <h1>Find the pause that feels like part of the story.</h1>
          </div>
          <button className="sample-button" type="button" onClick={runDemo} disabled={isBusy}>
            <Play size={17} fill="currentColor" />
            Run sample drama
          </button>
        </section>

        <section className="workbench">
          <aside className="control-panel">
            <div className="panel-heading">
              <span>01</span>
              <div>
                <h2>Ingest</h2>
                <p>Upload a Bengali drama</p>
              </div>
            </div>

            <button className="dropzone" type="button" onClick={() => videoInput.current?.click()} disabled={STATIC_MODE}>
              <Upload size={22} />
              <strong>{STATIC_MODE ? 'Sample drama bundled' : selectedVideo?.name ?? 'Choose a video'}</strong>
              <span>{STATIC_MODE ? 'Uploads available in Docker mode' : selectedVideo ? `${(selectedVideo.size / 1024 / 1024).toFixed(1)} MB` : 'MP4, MOV, MKV or WEBM · up to 400 MB'}</span>
            </button>
            <input
              ref={videoInput}
              type="file"
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
              hidden
              onChange={selectVideo}
            />

            <div className="policy-heading">
              <h3>Pacing policy</h3>
              <span>Guardrails enforced</span>
            </div>
            <label className="policy-field">
              <span>Maximum breaks / hour</span>
              <input
                type="number"
                min="1"
                max="12"
                value={policy.maxBreaksPerHour}
                onChange={(event) => setPolicy({ ...policy, maxBreaksPerHour: Number(event.target.value) })}
              />
            </label>
            <label className="policy-field">
              <span>Minimum gap</span>
              <div><input
                type="number"
                min="30"
                max="1800"
                step="30"
                value={policy.minGapSeconds}
                onChange={(event) => setPolicy({ ...policy, minGapSeconds: Number(event.target.value) })}
              /><small>sec</small></div>
            </label>
            <label className="policy-field">
              <span>Maximum ad load</span>
              <div><input
                type="number"
                min="1"
                max="20"
                value={policy.maxAdLoadPercent}
                onChange={(event) => setPolicy({ ...policy, maxAdLoadPercent: Number(event.target.value) })}
              /><small>%</small></div>
            </label>

            <button className="catalogue-picker" type="button" onClick={() => catalogueInput.current?.click()} disabled={STATIC_MODE}>
              <FileJson size={17} />
              <span>{STATIC_MODE ? 'Bundled brand catalogue' : selectedCatalogue?.name ?? 'Use a custom brand catalogue'}</span>
              <ChevronRight size={16} />
            </button>
            <input
              ref={catalogueInput}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(event) => setSelectedCatalogue(event.target.files?.[0] ?? null)}
            />

            <button className="analyse-button" type="button" onClick={STATIC_MODE ? runDemo : analyseUpload} disabled={isBusy}>
              {isBusy ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
              {isBusy ? 'Analysing story' : STATIC_MODE ? 'Apply policy to sample' : 'Analyse placement'}
            </button>
          </aside>

          <div className="stage-panel">
            {result ? (
              <>
                <AdPlayer key={result.job_id} result={result} onTimeChange={setPlayhead} />
                <div className="story-timeline" aria-label="Scene and ad break timeline">
                  <div className="timeline-labels">
                    <span>STORY MAP</span>
                    <span>{formatTime(playhead)} / {formatTime(result.duration_seconds)}</span>
                  </div>
                  <div className="timeline-track">
                    {result.scenes.map((scene, index) => (
                      <div
                        className={`scene-segment scene-${index % 4}`}
                        key={scene.id}
                        style={{ width: `${(scene.duration / result.duration_seconds) * 100}%` }}
                        title={`${formatTime(scene.start)} · ${scene.dominant_activity}`}
                      />
                    ))}
                    {result.breaks.map((slot) => (
                      <span
                        className="break-marker"
                        key={slot.id}
                        style={{ left: `${(slot.timestamp / result.duration_seconds) * 100}%` }}
                        title={`${slot.brand.name} at ${formatTime(slot.timestamp)}`}
                      />
                    ))}
                    <span className="playhead" style={{ left: `${(playhead / result.duration_seconds) * 100}%` }} />
                  </div>
                </div>
                <div className="metric-strip">
                  <div><Film size={17} /><span>Scenes<strong>{result.summary.scene_count}</strong></span></div>
                  <div><ShieldCheck size={17} /><span>Safe boundaries<strong>{result.summary.safe_candidate_count}</strong></span></div>
                  <div><Activity size={17} /><span>Scheduled<strong>{result.summary.break_count}</strong></span></div>
                  <div><Gauge size={17} /><span>Ad load<strong>{result.summary.ad_load_percent.toFixed(1)}%</strong></span></div>
                </div>
              </>
            ) : (
              <div className="empty-stage">
                {isBusy ? (
                  <>
                    <div className="analysis-pulse"><span /></div>
                    <p>{job?.stage ?? 'Preparing analysis'}</p>
                    <strong>{Math.round(progress * 100)}%</strong>
                    <div className="progress-track"><span style={{ width: `${progress * 100}%` }} /></div>
                  </>
                ) : (
                  <>
                    <div className="film-frame"><Film size={36} /></div>
                    <h2>Your story map appears here</h2>
                    <p>Run the sample or upload a drama to inspect scenes, safe boundaries and contextual matches.</p>
                  </>
                )}
              </div>
            )}
          </div>

          <aside className="insight-panel">
            <div className="panel-heading">
              <span>02</span>
              <div>
                <h2>Decisions</h2>
                <p>Every cut is auditable</p>
              </div>
            </div>

            <div className="tabs" role="tablist" aria-label="Analysis details">
              {(['breaks', 'scenes', 'safety', 'catalogue'] as InsightTab[]).map((tab) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab}
                  className={activeTab === tab ? 'active' : ''}
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>

            <div className="insight-scroll">
              {!result && activeTab !== 'catalogue' && (
                <div className="waiting-copy"><Clock3 size={20} /><p>Analysis decisions will appear after processing.</p></div>
              )}

              {result && activeTab === 'breaks' && result.breaks.map((slot, index) => (
                <article className="break-row" key={slot.id}>
                  <div className="row-index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="row-main">
                    <div className="row-title"><strong>{formatTime(slot.timestamp)}</strong><span>{scoreLabel(slot.score)} cut</span></div>
                    <div className="brand-match"><i style={{ background: slot.brand.color }} /><span>{slot.brand.name}</span><small>{Math.round(slot.match_score * 100)}% match</small></div>
                    <p>{slot.why[0]}</p>
                  </div>
                </article>
              ))}

              {result && activeTab === 'breaks' && result.breaks.length === 0 && (
                <div className="waiting-copy"><ShieldCheck size={20} /><p>No boundary passed every safety and pacing rule. No ad was forced.</p></div>
              )}

              {result && activeTab === 'scenes' && result.scenes.map((scene) => (
                <article className="scene-row" key={scene.id}>
                  <div><span>{formatTime(scene.start)}–{formatTime(scene.end)}</span><small>{scene.mood}</small></div>
                  <strong>{scene.dominant_activity}</strong>
                  <p>{scene.description}</p>
                  <div className="tag-list">{scene.contexts.slice(0, 3).map((context) => <span key={context}>{context}</span>)}</div>
                </article>
              ))}

              {result && activeTab === 'safety' && result.candidates.map((candidate) => (
                <article className={`safety-row ${candidate.is_safe ? 'safe' : 'blocked'}`} key={candidate.id}>
                  <div>{candidate.is_safe ? <Check size={16} /> : <AlertTriangle size={16} />}</div>
                  <section>
                    <strong>{formatTime(candidate.timestamp)} · {Math.round(candidate.interruptibility_score * 100)}</strong>
                    <span>{candidate.decision}</span>
                    <p>{candidate.reasons.join(' · ')}</p>
                  </section>
                </article>
              ))}

              {activeTab === 'catalogue' && catalogue.map((brand) => (
                <article className="catalogue-row" key={brand.id}>
                  <i style={{ background: brand.color }} />
                  <div><strong>{brand.name}</strong><span>{brand.category}</span><p>{brand.target_activities.slice(0, 3).join(' · ')}</p></div>
                </article>
              ))}
            </div>

            {result && (
              <div className="exports">
                <a href={result.manifest_url} download><Download size={16} />VMAP</a>
                <a href={result.debug_url} download><FileJson size={16} />Debug JSON</a>
              </div>
            )}
          </aside>
        </section>

        {error && <div className="error-banner" role="alert"><AlertTriangle size={18} />{error}</div>}

        <section className="trust-strip">
          <div><ShieldCheck size={20} /><span><strong>Fail closed</strong>Negative context is a hard block</span></div>
          <div><Activity size={20} /><span><strong>Dialogue aware</strong>Speech overlap rejects a cut</span></div>
          <div><Sparkles size={20} /><span><strong>Open catalogue</strong>New brands need no code change</span></div>
          <div className="model-note"><span>MODEL PROFILE</span><strong>{result?.models.visual ?? 'SmolVLM2 256M · Whisper tiny'}</strong></div>
        </section>

        <PipelineExplainer />
      </main>
    </div>
  )
}

export default App