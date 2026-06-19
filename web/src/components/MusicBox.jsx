import { useState, useRef, useEffect } from "react"
import { ChevronDown, Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, Music as MusicIcon } from "lucide-react"

export default function MusicBox() {
  const [expanded, setExpanded] = useState(false)
  const [tracks, setTracks] = useState([])
  const [currentIdx, setCurrentIdx] = useState(-1)
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(0.6)
  const [muted, setMuted] = useState(false)
  const [loading, setLoading] = useState(false)
  const audioRef = useRef(null)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [loaded, setLoaded] = useState(false)

  // Load tracks list
  useEffect(() => {
    fetch("/music/tracks.json")
      .then(r => r.json())
      .then(data => { setTracks(data); setLoaded(true) })
      .catch(() => setLoaded(true))
  }, [])

  const currentTrack = tracks[currentIdx]

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !currentTrack) return
    // idx 变化时重新加载 src
    const needReload = audio.dataset.idx !== String(currentIdx)
    if (needReload) {
      audio.src = "/music/" + currentTrack.file
      audio.dataset.idx = String(currentIdx)
    }
    audio.volume = muted ? 0 : volume
    if (playing) {
      setLoading(true)
      audio.play().catch(() => { setPlaying(false); setLoading(false) })
    } else if (needReload) {
      // 刚加载但不需要播放，暂停
      audio.pause()
    }
  }, [currentIdx, playing])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.volume = muted ? 0 : volume
  }, [volume, muted])

  const togglePlay = () => {
    const audio = audioRef.current
    if (!audio || !currentTrack) return
    if (playing) {
      audio.pause()
      setPlaying(false)
    } else {
      setLoading(true)
      audio.play().catch(() => { setPlaying(false); setLoading(false) })
      setPlaying(true)
    }
  }

  const prevTrack = () => {
    if (tracks.length === 0) return
    setPlaying(true)
    setCurrentIdx((currentIdx - 1 + tracks.length) % tracks.length)
  }

  const nextTrack = () => {
    if (tracks.length === 0) return
    setPlaying(true)
    setCurrentIdx((currentIdx + 1) % tracks.length)
  }

  const selectTrack = (idx) => {
    setCurrentIdx(idx)
    setPlaying(true)
  }

  const handleTimeUpdate = () => {
    const audio = audioRef.current
    if (!audio) return
    setProgress(audio.currentTime)
    setDuration(audio.duration || 0)
  }

  const handleSeek = (e) => {
    const audio = audioRef.current
    if (!audio || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    audio.currentTime = pct * duration
  }

  const handleEnded = () => {
    if (tracks.length === 1) {
      // 单曲：直接重播
      const audio = audioRef.current
      if (audio) {
        audio.currentTime = 0
        audio.play().catch(() => setPlaying(false))
      }
    } else {
      nextTrack()
    }
  }

  const formatTime = (s) => {
    if (!s || isNaN(s)) return "0:00"
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, "0")}`
  }

  return (
    <>
      <audio ref={audioRef} onTimeUpdate={handleTimeUpdate} onEnded={handleEnded} onCanPlay={() => setLoading(false)} onError={() => { setPlaying(false); setLoading(false) }} />

      {/* Collapsed button - always visible */}
      {!expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="fixed bottom-4 right-4 z-50 flex items-center justify-center cursor-pointer transition-all duration-200 hover:scale-105"
          style={{
            width: "42px",
            height: "42px",
            background: "rgba(26,26,46,0.92)",
            border: "1px solid rgba(79,195,247,0.25)",
            clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))",
          }}
        >
          <MusicIcon size={18} style={{ color: "#4fc3f7" }} />
        </button>
      )}

      {/* Expanded panel */}
      {expanded && (
        <div
          className="fixed bottom-4 right-4 z-50 ark-fade-in"
          style={{
            width: "280px",
            background: "rgba(10,10,26,0.97)",
            border: "1px solid rgba(79,195,247,0.18)",
            backdropFilter: "blur(16px)",
            clipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: "1px solid rgba(79,195,247,0.1)" }}>
            <div className="flex items-center gap-2">
              <img src="/music-icon.png" alt="Music" className="w-3.5 h-3.5" />
              <span className="text-xs font-semibold tracking-[0.15em] uppercase" style={{ color: "#4fc3f7", fontFamily: "var(--font-display)" }}>Emperor's music channel</span>
            </div>
            <button onClick={() => setExpanded(false)} className="cursor-pointer p-0.5 transition-colors hover:text-white" style={{ color: "#5a6178" }}>
              <ChevronDown size={16} />
            </button>
          </div>

          {!loaded ? (
            <div className="px-4 py-6 text-center text-xs" style={{ color: "#5a6178" }}>加载中...</div>
          ) : tracks.length === 0 ? (
            <div className="px-4 py-6 text-center">
              <MusicIcon size={24} style={{ color: "#3a4050" }} className="mx-auto mb-2" />
              <p className="text-xs" style={{ color: "#5a6178" }}>暂无音乐</p>
              <p className="text-[10px] mt-1" style={{ color: "#3a4050" }}>将 mp3/m4a 文件放入 public/music/ 目录<br />并创建 tracks.json</p>
            </div>
          ) : (
            <>
              {/* Now playing */}
              <div className="px-4 py-3">
                <p className="text-xs mb-1" style={{ color: "#5a6178" }}>正在播放</p>
                <p className="text-sm text-white truncate font-medium">{currentTrack ? currentTrack.name : "未选择"}</p>
                {/* Progress bar */}
                {currentTrack && (
                  <div className="mt-2.5 flex items-center gap-2">
                    <span className="text-[10px] tabular-nums" style={{ color: "#5a6178", minWidth: "28px", textAlign: "right" }}>{formatTime(progress)}</span>
                    <div
                      className="flex-1 h-[3px] rounded-full cursor-pointer relative overflow-hidden"
                      style={{ background: "rgba(79,195,247,0.1)" }}
                      onClick={handleSeek}
                    >
                      <div
                        className="h-full rounded-full transition-all duration-100"
                        style={{ width: duration ? `${(progress / duration) * 100}%` : "0%", background: "#4fc3f7" }}
                      />
                    </div>
                    <span className="text-[10px] tabular-nums" style={{ color: "#5a6178", minWidth: "28px" }}>{formatTime(duration)}</span>
                  </div>
                )}
              </div>

              {/* Controls */}
              <div className="flex items-center justify-center gap-5 px-4 py-2">
                <button onClick={prevTrack} className="cursor-pointer p-1.5 transition-colors hover:text-white" style={{ color: "#8892b0" }}>
                  <SkipBack size={16} />
                </button>
                <button
                  onClick={togglePlay}
                  disabled={!currentTrack}
                  className="cursor-pointer flex items-center justify-center transition-all disabled:opacity-30"
                  style={{
                    width: "36px",
                    height: "36px",
                    background: playing ? "rgba(79,195,247,0.15)" : "rgba(79,195,247,0.08)",
                    border: "1px solid rgba(79,195,247,0.3)",
                    clipPath: "polygon(0 0, calc(100% - 5px) 0, 100% 5px, 100% 100%, 5px 100%, 0 calc(100% - 5px))",
                    color: "#4fc3f7",
                  }}
                >
                  {loading ? <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent animate-spin rounded-full" /> : playing ? <Pause size={15} /> : <Play size={15} />}
                </button>
                <button onClick={nextTrack} className="cursor-pointer p-1.5 transition-colors hover:text-white" style={{ color: "#8892b0" }}>
                  <SkipForward size={16} />
                </button>
                <button
                  onClick={() => setMuted(!muted)}
                  className="cursor-pointer p-1.5 transition-colors hover:text-white"
                  style={{ color: muted ? "#3a4050" : "#8892b0" }}
                >
                  {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
                </button>
              </div>

              {/* Volume slider */}
              {!muted && (
                <div className="px-6 pb-2">
                  <input
                    type="range"
                    min="0" max="1" step="0.05"
                    value={volume}
                    onChange={(e) => setVolume(parseFloat(e.target.value))}
                    className="w-full h-[3px] rounded-full appearance-none cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, #4fc3f7 ${volume * 100}%, rgba(79,195,247,0.12) ${volume * 100}%)`,
                      accentColor: "#4fc3f7",
                    }}
                  />
                </div>
              )}

              {/* Track list */}
              <div className="max-h-36 overflow-y-auto px-2 pb-2 mt-1" style={{ borderTop: "1px solid rgba(79,195,247,0.06)" }}>
                {tracks.map((t, i) => (
                  <button
                    key={i}
                    onClick={() => selectTrack(i)}
                    className="w-full text-left px-2.5 py-1.5 text-xs truncate cursor-pointer transition-colors rounded-sm"
                    style={{
                      color: i === currentIdx ? "#4fc3f7" : "#8892b0",
                      background: i === currentIdx ? "rgba(79,195,247,0.06)" : "transparent",
                    }}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {i === currentIdx && playing && <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#4fc3f7] animate-pulse" />}
                      {t.name}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </>
  )
}
