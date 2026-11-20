import { useRef, useState } from "react";
import { Headphones } from "lucide-react";
import type { Segment } from "../api/client";

function time(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export default function RecordingPlayer({ src, track }: { src: string; track: Segment[] }) {
  const player = useRef<HTMLAudioElement>(null);
  const [speed, setSpeed] = useState(1);
  const [error, setError] = useState("");
  const [position, setPosition] = useState(-1);

  function jump(segment: Segment) {
    const audio = player.current;
    if (!audio) return;
    audio.currentTime = segment.start;
    void audio.play().catch(() => setError("Press Play to start at the selected timestamp."));
  }

  return (
    <div className="recording-player">
      <div className="player-heading">
        <strong><Headphones size={17} aria-hidden="true" />Original recording</strong>
        <label>Speed <select aria-label="Playback speed" value={speed} onChange={(event) => {
          const rate = Number(event.target.value);
          setSpeed(rate);
          if (player.current) player.current.playbackRate = rate;
        }}>
          {[0.75, 1, 1.25, 1.5, 2].map((rate) => <option value={rate} key={rate}>{rate}×</option>)}
        </select></label>
      </div>
      <audio aria-label="Original recording" controls preload="metadata" src={src} ref={player}
        onTimeUpdate={() => setPosition(player.current?.currentTime ?? -1)}
        onLoadedMetadata={() => { if (player.current) player.current.playbackRate = speed; }}
        onError={() => setError("Your browser could not play this recording format. MP3 and WAV usually work.")} />
      {!!track.length && <details className="recording-timeline">
        <summary>Jump to a transcript timestamp</summary>
        <div>
          {track.map((segment, index) => (
            <button key={index} type="button" aria-current={position >= segment.start && position < segment.end || undefined}
              onClick={() => jump(segment)}><small>{time(segment.start)}</small><span>{segment.text}</span></button>
          ))}
        </div>
      </details>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
