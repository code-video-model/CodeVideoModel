import { useEffect, useRef, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Reactor, type ReactorStatus } from "@reactor-team/js-sdk";
import { Logo } from "@reactor-team/ui";
import { EXAMPLES, EXAMPLE_SOURCE, loadExample } from "./examples";
import { ClipPlayer, type ClipPlayerHandle } from "./clip-player";
import "./style.css";

type State = {has_proxy: boolean; has_reference: boolean; job_id: number; phase: string; denoising_step: number; compute_seconds: number};
function Workspace({endpoint, endpointControl}: {endpoint: string; endpointControl: ReactNode}) {
  const [client] = useState(() => new Reactor({modelName:"code-video-model", local:true, apiUrl:endpoint,
    controlRequestTimeoutMs:360000, modelTracks:[
      {name:"main_video",kind:"video",direction:"recvonly"}, {name:"main_audio",kind:"audio",direction:"recvonly"}
    ]}));
  const [status, setStatus] = useState<ReactorStatus>("disconnected");
  const player = useRef<ClipPlayerHandle>(null);
  const [sessionId, setSessionId] = useState<string | undefined>(), [clipReady, setClipReady] = useState(false);
  const send = client.sendCommand.bind(client), upload = client.uploadFile.bind(client);
  const disconnect = () => client.disconnect();
  async function connect() {
    await client.connect();
    // Saved results are keyed by the local Runtime's session descriptor.
    const response = await fetch(`${endpoint.replace(/\/$/, "")}/session`);
    if (!response.ok) throw new Error(`Session details: HTTP ${response.status}`);
    const session = await response.json();
    if (!session.session_id || !session.step_results?.enabled) {
      throw new Error("Enable runtime.step_results in reactor.yaml and restart the service.");
    }
  }
  const [state, setState] = useState<State | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [prompt, setPrompt] = useState(""), [seed, setSeed] = useState(42), [keep, setKeep] = useState(5);
  const [mode, setMode] = useState("proxy"), [proxy, setProxy] = useState<File | null>(null), [reference, setReference] = useState<File | null>(null);
  const [selection, setSelection] = useState("custom"), [filesKey, setFilesKey] = useState(0);
  const [referencePreview, setReferencePreview] = useState("");
  const [proxyPreview, setProxyPreview] = useState("");
  useEffect(() => {
    if (!proxy || mode !== "proxy") { setProxyPreview(""); return; }
    const url = URL.createObjectURL(proxy); setProxyPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [proxy, mode]);
  const [operation, setOperation] = useState(""), [health, setHealth] = useState("checking");
  const [clock, setClock] = useState(Date.now()), [phaseSince, setPhaseSince] = useState(Date.now());
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response = await fetch(`${endpoint.replace(/\/$/, "")}/health`, {signal: AbortSignal.timeout(4000)});
        if (!response.ok) throw new Error("Health unavailable");
        const result = await response.json();
        if (!stopped) setHealth(result.state);
      } catch { if (!stopped) setHealth("unreachable"); }
      if (!stopped) timer = setTimeout(poll, 5000);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [endpoint]);
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (!reference) { setReferencePreview(""); return; }
    const url = URL.createObjectURL(reference);
    setReferencePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [reference]);
  useEffect(() => {
    client.on("statusChanged", setStatus);
    client.on("error", e => setError(e.message));
    client.on("message", message => { if (message.type === "state_update") setState(message.data as State); });
    return () => { client[Symbol.dispose](); };
  }, [client]);
  const ready = status === "ready", generating = ["queued", "denoising", "decoding"].includes(state?.phase ?? "");
  useEffect(() => {
    if (!ready) return;
    // Runtime publishes the saved-result session ID with each completed save.
    const events = new EventSource(`${endpoint.replace(/\/$/, "")}/events`);
    events.onmessage = message => {
      const event = JSON.parse(message.data);
      if (event.type === "transition" && event.event === "step_result_ready") {
        setSessionId(event.detail.session_id);
      }
    };
    return () => events.close();
  }, [ready, endpoint]);
  let phase = "Choose your inputs", detail = "Choose a demo or upload your scene, reference and prompt.";
  if (!ready) {
    phase = health === "loading" ? "Loading model weights" : status === "connecting" ? "Connecting" : status === "waiting" ? "Waiting for session" : health === "unreachable" ? "Runtime unreachable" : health === "checking" ? "Checking Runtime" : "Ready to connect";
    detail = health === "unreachable" ? "Check the Runtime URL in the top bar and your SSH forwards." : "Connect to the Runtime to generate a video.";
  } else if (proxy && reference && prompt.trim()) { phase = "Ready to generate"; detail = "Your inputs are selected. Press Generate video to begin."; }
  if (state?.phase === "complete" && ready) {
    phase = clipReady ? "Video ready" : "Receiving video & audio";
    detail = clipReady ? "Press Play to watch your video." : "Preparing playback…";
  }
  if (state?.phase === "cancelled" && ready) { phase = "Cancelled"; detail = "Change your inputs or start a new independent clip."; }
  if (operation) { phase = operation; detail = operation === "Rendering scene" ? "CPU renderer is executing your scene. This can take 2–5 minutes." : "Keep this tab open. Inputs are processed in order."; }
  if (generating && ready && operation !== "Cancelling") {
    phase = state?.phase === "decoding" ? "Decoding video & audio" : state?.phase === "queued" || state?.denoising_step === 0 ? "Preparing model inputs" : "Generating video";
    detail = state?.phase === "decoding" ? "All 20 updates finished. Preparing the complete clip for playback." : "The complete video appears after all 20 updates and decoding.";
  }
  if (error) { phase = "Attention needed"; detail = error; }
  const receiving = ready && state?.phase === "complete" && !clipReady && !error;
  const working = !error && (busy || generating || receiving || status === "connecting" || status === "waiting" || health === "loading");
  useEffect(() => { setPhaseSince(Date.now()); }, [phase]);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); } catch(e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); setOperation(""); }
  }
  function clearInputs() {
    setSelection("custom"); setProxy(null); setReference(null); setPrompt("");
    setMode("scene"); setFilesKey(value => value + 1); setError("");
  }
  async function selectExample(id: string) {
    clearInputs();
    await perform(async () => {
      setOperation("Loading example");
      const example = await loadExample(id);
      setMode("proxy"); setProxy(example.proxy); setReference(example.reference);
      setPrompt(example.prompt); setSeed(42); setKeep(5); setSelection(id);
    });
  }
  return <main className="shell">
    <header><a className="brand" href="https://reactor.inc" target="_blank" rel="noreferrer" aria-label="Reactor"><Logo variant="symbol" color="white" height={18} aria-hidden="true"/></a><i/><strong>Code Video Model</strong>{endpointControl}<span className="connection"><b className={`dot ${ready ? "online" : ""}`}/>{ready ? "Connected" : status}</span>
      <button disabled={busy || status === "connecting" || status === "waiting"} onClick={() => void perform(async () => {
        if (ready) { player.current?.stop(); await disconnect(); setSessionId(undefined); setState(null); } else await connect();
      })}>{ready ? "Disconnect" : "Connect"}</button></header>
    <div className="workspace"><aside><div className="sidebar-scroll">
      <div className="eyebrow">01 / SET THE SCENE</div><h1>From code to cinema.</h1><p className="hint">Choose a demo, or bring your own scene. Generate only when you are ready.</p>
      <div className="gallery" aria-label="Example scenes">{EXAMPLES.map(example => <button className="example" key={example.id}
        aria-pressed={selection === example.id} disabled={busy || generating} onClick={() => void selectExample(example.id)}>
        <img src={`${EXAMPLE_SOURCE}/${example.id}/reference.png`} alt="" loading="lazy"/>
        <strong>{example.title}</strong><small>{selection === example.id ? "Selected" : "Load example ↗"}</small>
      </button>)}</div>
      <button className="custom-button" disabled={busy || generating} onClick={clearInputs}>＋ Upload your own</button>
      <p className="selection">{selection === "custom" ? "Custom inputs" : `Selected: ${EXAMPLES.find(e => e.id === selection)?.title}`}</p>
      <label>Structure input<select value={mode} disabled={generating || busy} onChange={e => {setMode(e.target.value); setProxy(null); setSelection("custom");}}><option value="proxy">Proxy video (.mp4)</option><option value="scene">Three.js scene (.zip)</option></select></label>
      <label className="upload"><span className="upload-icon">＋</span><span><strong>{proxy?.name ?? (mode === "scene" ? "Upload scene ZIP" : "Upload proxy video")}</strong><small>{mode === "proxy" ? "960×544 · 124 frames · 24 FPS" : "case/index.html + local modules"}</small></span>
        <input aria-label="Structure file" key={`${mode}-${filesKey}`} type="file" accept={mode === "proxy" ? ".mp4" : ".zip"} disabled={generating || busy} onChange={e => {setProxy(e.target.files?.[0] ?? null); setSelection("custom");}}/></label>
      {proxyPreview && <div className="proxy-preview"><span className="eyebrow">INPUT VIDEO · STRUCTURE REFERENCE</span><video key={proxyPreview} src={proxyPreview} controls playsInline muted preload="metadata" aria-label="Input video preview"/></div>}
      <label className="upload">{referencePreview ? <img className="reference-preview" src={referencePreview} alt="Selected style reference"/> : <span className="upload-icon">＋</span>}<span><strong>{reference?.name ?? "Upload style reference"}</strong><small>PNG or JPEG · visual appearance</small></span><input aria-label="Style reference" key={filesKey} type="file" accept="image/png,image/jpeg" disabled={generating || busy} onChange={e => {setReference(e.target.files?.[0] ?? null); setSelection("custom");}}/></label>
      <label>Prompt<textarea rows={4} value={prompt} placeholder="Describe the scene and motion…" maxLength={8000} disabled={generating || busy} onChange={e => setPrompt(e.target.value)}/></label>
      <details className="advanced"><summary>Generation settings</summary><div className="settings-grid">
      <label>Seed<input type="number" min={0} max={2147483647} value={seed} disabled={generating || busy} onChange={e => setSeed(Number(e.target.value))}/></label>
      <label>Proxy-conditioned updates (of 20)<input type="number" min={0} max={20} value={keep} disabled={generating || busy} onChange={e => setKeep(Number(e.target.value))}/></label>
      </div></details>
      <p className="attribution">Examples: <a href="https://huggingface.co/datasets/code-video-model/CodeVideoBench" target="_blank" rel="noreferrer">CodeVideoBench contributors</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>. Unmodified upstream assets; internet required to load examples.</p>
      </div><div className="sidebar-actions">
      <button className="primary" disabled={!ready || busy || generating || receiving || !proxy || !reference || !prompt.trim()} onClick={() => void perform(async () => {
        player.current?.stop();
        setOperation(mode === "scene" ? "Uploading scene ZIP" : "Uploading proxy video");
        const structure = await upload(proxy!);
        setOperation(mode === "scene" ? "Rendering scene" : "Validating proxy video");
        await send(mode === "proxy" ? "set_proxy" : "set_scene", mode === "proxy" ? {video: structure} : {scene: structure});
        setOperation("Uploading reference image");
        const image = await upload(reference!);
        setOperation("Validating reference image");
        await send("set_reference", {image});
        setOperation("Starting generation");
        await send("start", {prompt, seed, keep_steps: keep});
      })}>{busy || generating ? "Working…" : "Generate video"}</button>
      <button className="cancel" disabled={!ready || busy} onClick={() => {
        player.current?.stop();
        if (generating || receiving) void perform(async () => {setOperation("Cancelling"); await send("cancel", {});});
      }}>Cancel / stop playback</button>
      </div></aside><section className="stage-column">
      <div className="stage-heading"><div><div className="eyebrow">02 / GENERATED OUTPUT</div><h2>Your scene, reimagined.</h2></div><span className="tag">960 × 544 · 24 FPS</span></div>
      <div className="stage"><ClipPlayer ref={player} endpoint={endpoint} sessionId={sessionId} job={state?.job_id ?? 0} complete={ready && state?.phase === "complete"} onReady={setClipReady} onError={setError}/>
        {!clipReady && <div className="placeholder">{referencePreview && <img src={referencePreview} alt="Reference preview"/>}<div className="placeholder-copy"><span className="eyebrow">{referencePreview ? "REFERENCE PREVIEW" : "CODE VIDEO MODEL"}</span><div className={`stage-symbol ${working ? "spinning" : ""}`}>{working ? "" : "▷"}</div><h2>{phase}</h2><p>{detail}</p></div></div>}
      </div>
      <div className="phase-panel" role="status" aria-live="polite"><div className="phase-top"><div><b className={`dot ${working ? "working" : ready ? "online" : ""}`}/><strong>{phase}</strong></div><span>{working ? `${Math.max(0, Math.floor((clock - phaseSince) / 1000))}s in phase` : state ? `Job ${state.job_id}` : "No active job"}</span></div>
        <p>{detail}</p><div className="progress-line"><span>H3 updates</span><span>{state?.denoising_step ?? 0} / 20</span></div><progress aria-label="Completed denoising updates" max={20} value={state?.denoising_step ?? 0}/>
        <div className="phase-footer"><span>{state ? `Job ${state.job_id} · ${state.compute_seconds.toFixed(1)} s model compute` : "Waiting for inputs"}</span><span>Prepare → Generate → Decode → Video ready</span></div>
      </div>
      {error && <div className="error" role="alert">{error}</div>}
      <footer><span>One complete 5.17-second clip · native audio</span><span>Built on Reactor</span></footer>
    </section></div>
  </main>;
}
function App() {
  const [endpoint, setEndpoint] = useState("http://localhost:8080"), [active, setActive] = useState(endpoint);
  const endpointControl = <form className="endpoint-inline" onSubmit={e => {e.preventDefault(); setActive(endpoint);}}>
    <label htmlFor="runtime-url">Runtime URL</label><input id="runtime-url" type="url" required value={endpoint} onChange={e => setEndpoint(e.target.value)}/><button>Use endpoint</button>
  </form>;
  return <Workspace key={active} endpoint={active} endpointControl={endpointControl}/>;
}
createRoot(document.getElementById("root")!).render(<App/>);
