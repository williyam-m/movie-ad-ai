import { useEffect, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  AudioLines,
  Braces,
  Cpu,
  FileVideo2,
  Route,
  ScanSearch,
} from 'lucide-react'

interface PipelineStage {
  label: string
  title: string
  description: string
  metric: string
  metricLabel: string
  technologies: string[]
  icon: LucideIcon
}

const PIPELINE_STAGES: PipelineStage[] = [
  {
    label: '01 / INGEST',
    title: 'Bound the input before analysis',
    description:
      'FastAPI streams multipart data to an isolated job directory in 1 MiB chunks. Container and MIME allowlists run first, and the transfer stops as soon as it crosses 400 MiB.',
    metric: '1 MiB',
    metricLabel: 'stream chunk',
    technologies: ['FastAPI', 'python-multipart', 'local job storage'],
    icon: FileVideo2,
  },
  {
    label: '02 / EVIDENCE',
    title: 'Measure cuts and silence with deterministic tools',
    description:
      'FFprobe reads duration once. FFmpeg then emits scene-change scores and silence intervals; nearby edits are merged so flashes and rapid cuts do not become false ad opportunities.',
    metric: '0.18',
    metricLabel: 'scene threshold',
    technologies: ['FFprobe', 'FFmpeg scene filter', 'silencedetect'],
    icon: ScanSearch,
  },
  {
    label: '03 / SPEECH',
    title: 'Build a dialogue exclusion map',
    description:
      'Timed subtitles are used when present. Otherwise faster-whisper tiny runs int8 on CPU with VAD and word timing. Any boundary overlapping speech is rejected before ranking.',
    metric: 'int8',
    metricLabel: 'CPU inference',
    technologies: ['faster-whisper', 'CTranslate2', 'subtitle parser'],
    icon: AudioLines,
  },
  {
    label: '04 / VISION',
    title: 'Describe only the frames that matter',
    description:
      'A midpoint frame represents each bounded scene. SmolVLM2 returns compact activity, mood and safety context JSON; extraction stops when VLM is disabled, fails, or reaches the scene budget.',
    metric: '36 max',
    metricLabel: 'visual scenes',
    technologies: ['SmolVLM2 256M', 'Transformers', 'PyTorch CPU'],
    icon: Cpu,
  },
  {
    label: '05 / DECISION',
    title: 'Gate first, rank second',
    description:
      'Silence, dialogue and programme-edge checks are hard constraints. Multilingual MiniLM compares surviving scene context with catalogue data, while every negative-context match removes the brand outright.',
    metric: '0.68',
    metricLabel: 'activity weight',
    technologies: ['MiniLM L12', 'normalized embeddings', 'pacing policy'],
    icon: Route,
  },
  {
    label: '06 / DELIVERY',
    title: 'Emit a portable, auditable schedule',
    description:
      'The worker writes every accepted and rejected decision to debug JSON, serializes selected breaks as VMAP with inline VAST, and returns media URLs to the ad-resume player.',
    metric: 'VMAP 1.0',
    metricLabel: 'delivery contract',
    technologies: ['VAST 4.2', 'debug JSON', 'React player'],
    icon: Braces,
  },
]

export function PipelineExplainer() {
  const [activeIndex, setActiveIndex] = useState(0)
  const stageRefs = useRef<Array<HTMLElement | null>>([])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)
        if (!visible[0]) return
        setActiveIndex(Number((visible[0].target as HTMLElement).dataset.stage))
      },
      { rootMargin: '-22% 0px -52%', threshold: [0.15, 0.4, 0.7] },
    )

    stageRefs.current.forEach((stage) => {
      if (stage) observer.observe(stage)
    })
    return () => observer.disconnect()
  }, [])

  const activeStage = PIPELINE_STAGES[activeIndex]
  const ActiveIcon = activeStage.icon

  return (
    <section className="pipeline-explainer" aria-labelledby="pipeline-title">
      <header className="pipeline-heading">
        <div>
          <p className="eyebrow">EXECUTION TRACE / CPU-FIRST</p>
          <h2 id="pipeline-title">Inside the analysis worker</h2>
        </div>
        <p>
          Scroll through the exact path from uploaded bytes to a standards-ready ad
          schedule. Model output contributes context; deterministic evidence keeps
          authority over safety and pacing.
        </p>
      </header>

      <div className="pipeline-layout">
        <aside className="pipeline-console" aria-label="Active backend stage">
          <div className="console-status">
            <span>ACTIVE NODE</span>
            <strong>{String(activeIndex + 1).padStart(2, '0')}</strong>
          </div>
          <div className="console-icon"><ActiveIcon size={34} /></div>
          <p>{activeStage.label}</p>
          <h3>{activeStage.title}</h3>
          <div className="console-meter" aria-hidden="true">
            <span style={{ width: `${((activeIndex + 1) / PIPELINE_STAGES.length) * 100}%` }} />
          </div>
          <dl>
            <div><dt>Runtime</dt><dd>1 worker / 2 CPU threads</dd></div>
            <div><dt>Fallback</dt><dd>lexical + deterministic gates</dd></div>
            <div><dt>Data path</dt><dd>local processing only</dd></div>
          </dl>
        </aside>

        <ol className="pipeline-stages">
          {PIPELINE_STAGES.map((stage, index) => {
            const StageIcon = stage.icon
            return (
              <li
                className={index === activeIndex ? 'active' : ''}
                data-stage={index}
                key={stage.label}
                ref={(node) => { stageRefs.current[index] = node }}
                aria-current={index === activeIndex ? 'step' : undefined}
              >
                <div className="stage-index"><StageIcon size={19} /></div>
                <article>
                  <span>{stage.label}</span>
                  <h3>{stage.title}</h3>
                  <p>{stage.description}</p>
                  <div className="stage-tech">
                    {stage.technologies.map((technology) => <code key={technology}>{technology}</code>)}
                  </div>
                </article>
                <div className="stage-metric"><strong>{stage.metric}</strong><span>{stage.metricLabel}</span></div>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}