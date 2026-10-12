import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

export type ClipPlayerHandle = { stop: () => void };
type Props = {endpoint: string; sessionId: string | undefined; job: number; complete: boolean;
  onReady: (ready: boolean) => void; onError: (error: string) => void};
type SavedStep = {files: {name: string; size: number}[]; save_error: string | null;
  messages: {type: string; data: {job_id?: number; phase?: string}}[]};

/** Play the finite MP4 saved by Runtime, independently of live WebRTC playout. */
export const ClipPlayer = forwardRef<ClipPlayerHandle, Props>(function ClipPlayer(
  {endpoint, sessionId, job, complete, onReady, onError}, ref) {
  const player = useRef<HTMLVideoElement>(null);
  const [url, setUrl] = useState("");
  const callbacks = useRef({onReady, onError});
  callbacks.current = {onReady, onError};
  useImperativeHandle(ref, () => ({stop() {
    if (player.current) { player.current.pause(); player.current.currentTime = 0; }
  }}), []);
  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    let objectUrl = "";
    setUrl(""); callbacks.current.onReady(false);
    if (!complete || !sessionId) return;
    const base = `${endpoint.replace(/\/$/, "")}/sessions/${encodeURIComponent(sessionId)}/steps`;
    const checked = new Set<number>();
    async function receive() {
      const deadline = Date.now() + 120000;
      while (!signal.aborted && Date.now() < deadline) {
        const listing = await fetch(base, {signal});
        if (!listing.ok && listing.status !== 404) throw new Error(`Video results: HTTP ${listing.status}`);
        const steps: number[] = listing.ok ? (await listing.json()).steps : [];
        for (const step of steps.slice().reverse()) {
          if (checked.has(step)) continue;
          const response = await fetch(`${base}/${step}`, {signal});
          if (response.status === 404) continue;
          if (!response.ok) throw new Error(`Video result: HTTP ${response.status}`);
          const result: SavedStep = await response.json();
          checked.add(step);
          if (!result.messages.some(m => m.type === "state_update" && m.data.job_id === job && m.data.phase === "complete")) continue;
          if (result.save_error) throw new Error(`Video export failed: ${result.save_error}`);
          const file = result.files.find(f => f.name === "output.mp4");
          if (!file) throw new Error("The completed result has no video file.");
          const media = await fetch(`${base}/${step}/output.mp4`, {signal});
          if (!media.ok) throw new Error(`Video download: HTTP ${media.status}`);
          const blob = await media.blob();
          if (blob.size !== file.size) throw new Error("Video download incomplete. Please reconnect to retry.");
          if (signal.aborted) return;
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
          return;
        }
        await new Promise<void>(resolve => {
          const done = () => { clearTimeout(timer); signal.removeEventListener("abort", done); resolve(); };
          const timer = setTimeout(done, 500);
          signal.addEventListener("abort", done, {once:true});
        });
      }
      if (!signal.aborted) throw new Error("Video export is unavailable. Check that Runtime step results are enabled.");
    }
    void receive().catch(error => { if (!signal.aborted) callbacks.current.onError(String(error.message ?? error)); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [endpoint, sessionId, job, complete]);
  return <video ref={player} src={url || undefined} className="video" playsInline controls
    onLoadedMetadata={() => callbacks.current.onReady(true)}
    onError={() => { if (url) callbacks.current.onError("This browser could not open the video."); }}/>
});
