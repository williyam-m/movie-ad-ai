import { useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Pause, Play, RotateCcw, Volume2 } from 'lucide-react'
import type { AnalysisResult, BreakSlot } from '../types'

interface AdPlayerProps {
  result: AnalysisResult
  onTimeChange: (time: number) => void
}

function formatTime(seconds: number): string {
  const rounded = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const remainder = rounded % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`
}

export function AdPlayer({ result, onTimeChange }: AdPlayerProps) {
  const contentRef = useRef<HTMLVideoElement>(null)
  const adRef = useRef<HTMLVideoElement>(null)
  const [activeBreak, setActiveBreak] = useState<BreakSlot | null>(null)
  const [playedBreaks, setPlayedBreaks] = useState<Set<string>>(new Set())
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const triggerBreak = (slot: BreakSlot) => {
    const content = contentRef.current
    if (!content) return
    content.pause()
    content.currentTime = slot.timestamp
    setPlayedBreaks((current) => new Set(current).add(slot.id))
    setActiveBreak(slot)
    setIsPlaying(false)
  }

  const handleTimeUpdate = () => {
    const content = contentRef.current
    if (!content || activeBreak) return
    const time = content.currentTime
    setCurrentTime(time)
    onTimeChange(time)
    const nextBreak = result.breaks.find(
      (slot) => !playedBreaks.has(slot.id) && time >= slot.timestamp - 0.18,
    )
    if (nextBreak) triggerBreak(nextBreak)
  }

  const finishAd = async () => {
    setActiveBreak(null)
    const content = contentRef.current
    if (!content) return
    try {
      await content.play()
      setIsPlaying(true)
    } catch {
      setIsPlaying(false)
    }
  }

  const togglePlayback = async () => {
    const player = activeBreak ? adRef.current : contentRef.current
    if (!player) return
    if (player.paused) {
      await player.play()
      setIsPlaying(true)
    } else {
      player.pause()
      setIsPlaying(false)
    }
  }

  const restart = () => {
    const content = contentRef.current
    if (!content) return
    content.pause()
    content.currentTime = 0
    setCurrentTime(0)
    setPlayedBreaks(new Set())
    setActiveBreak(null)
    setIsPlaying(false)
    onTimeChange(0)
  }

  return (
    <div className="player-shell">
      <div className="video-stage">
        <video
          ref={contentRef}
          key={result.media_url}
          src={result.media_url}
          preload="metadata"
          playsInline
          onTimeUpdate={handleTimeUpdate}
          onPlay={() => setIsPlaying(true)}
          onPause={() => !activeBreak && setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
        />

        {activeBreak && (
          <div className="ad-stage" style={{ '--brand': activeBreak.brand.color } as CSSProperties}>
            <video
              ref={adRef}
              key={activeBreak.id}
              src={activeBreak.creative_url}
              autoPlay
              playsInline
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              onEnded={finishAd}
              onError={finishAd}
            />
            <div className="ad-chrome">
              <span>AD {result.breaks.findIndex((item) => item.id === activeBreak.id) + 1} / {result.breaks.length}</span>
              <span>Content resumes automatically</span>
            </div>
            <div className="creative-copy">
              <p>{activeBreak.brand.category}</p>
              <h2>{activeBreak.brand.name}</h2>
              <span>{activeBreak.brand.tagline}</span>
            </div>
          </div>
        )}

        {!isPlaying && !activeBreak && (
          <button className="stage-play" type="button" onClick={togglePlayback} aria-label="Play video">
            <Play fill="currentColor" size={28} />
          </button>
        )}
      </div>

      <div className="player-controls">
        <button type="button" onClick={togglePlayback} aria-label={isPlaying ? 'Pause' : 'Play'}>
          {isPlaying ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
        </button>
        <button type="button" onClick={restart} aria-label="Restart with ad breaks">
          <RotateCcw size={17} />
        </button>
        <Volume2 size={17} aria-hidden="true" />
        <span>{activeBreak ? 'Advertisement' : `${formatTime(currentTime)} / ${formatTime(result.duration_seconds)}`}</span>
        <span className="player-mode">{result.breaks.length} scheduled break{result.breaks.length === 1 ? '' : 's'}</span>
      </div>
    </div>
  )
}