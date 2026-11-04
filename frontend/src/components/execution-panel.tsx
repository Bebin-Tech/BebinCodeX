'use client';
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronUp, ExternalLink, LoaderCircle, Play, RefreshCw, Square, Terminal, Monitor } from 'lucide-react';
import { api, body } from '@/lib/api';

interface Execution {
  id: string; kind: 'run' | 'preview'; path: string; revision: number;
  status: string; output: string; exit_code: number | null;
  preview_url: string | null; expires_at: string;
}
interface Props {
  projectId: string; activePath: string; htmlPath: string;
  revision: number; dirty: boolean; canWrite: boolean;
}

export function ExecutionPanel({ projectId, activePath, htmlPath, revision, dirty, canWrite }: Props) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<'output' | 'preview'>('output');
  const [run, setRun] = useState<Execution | null>(null);
  const [preview, setPreview] = useState<Execution | null>(null);
  const [action, setAction] = useState('');
  const [error, setError] = useState('');
  const [remaining, setRemaining] = useState(0);
  const actionRef = useRef(action);
  actionRef.current = action;
  const history = useQuery({
    queryKey: ['executions', projectId],
    queryFn: () => api<Execution[]>(`/projects/${projectId}/executions`),
  });
  useEffect(() => {
    if (!history.data) return;
    setRun(current => current || history.data.find(r => r.kind === 'run') || null);
    setPreview(current => current || history.data.find(r => r.kind === 'preview' && r.status === 'running') || null);
  }, [history.data]);
  useEffect(() => {
    if (preview?.status !== 'running') return;
    const tick = () => {
      const seconds = Math.max(0, Math.ceil((Date.parse(preview.expires_at) - Date.now()) / 1000));
      setRemaining(seconds);
      if (!seconds) setPreview(current => current ? { ...current, status: 'expired', preview_url: null } : current);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [preview?.id, preview?.status, preview?.expires_at]);

  async function perform(name: string, fn: () => Promise<void>) {
    setAction(name); setError(''); setExpanded(true);
    try { await fn(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Execution failed'); }
    finally { setAction(''); }
  }
  async function refreshPreview() {
    if (!preview) return;
    const result = await api<Execution>(`/executions/${preview.id}/preview`, { method: 'PUT' });
    setPreview(result);
  }
  useEffect(() => {
    if (!preview || preview.status !== 'running' || preview.revision === revision || !canWrite || error) return;
    let cancelled = false;
    let inFlight = false;
    const timer = setInterval(async () => {
      if (inFlight || actionRef.current) return;
      inFlight = true;
      setAction('refresh');
      try {
        const result = await api<Execution>(`/executions/${preview.id}/preview`, { method: 'PUT' });
        if (!cancelled) setPreview(result);
      } catch (e) { if (!cancelled) setError((e as Error).message); }
      finally { setAction(''); }
    }, 600);
    return () => { cancelled = true; clearInterval(timer); };
  }, [revision, preview?.id, preview?.revision, preview?.status, canWrite, error]);

  const canRun = /\.(py|js|mjs|cjs|ts|mts|cts)$/i.test(activePath);
  return <section className={`execution-panel ${expanded ? 'expanded' : ''}`} aria-label="Code execution and preview">
    <div className="execution-toolbar">
      <div className="execution-tabs">
        <button className={tab === 'output' && expanded ? 'selected' : ''} onClick={() => { setTab('output'); setExpanded(true); }}><Terminal size={14}/> Output</button>
        <button className={tab === 'preview' && expanded ? 'selected' : ''} onClick={() => { setTab('preview'); setExpanded(true); }}><Monitor size={14}/> Preview</button>
      </div>
      <div className="execution-controls">
        <button disabled={!canWrite || !!action || !canRun || dirty} title={dirty ? 'Save your edits before running' : 'Run the saved Python, JavaScript or TypeScript file'} onClick={() => { setTab('output'); perform('run', async () => {
          const result = await api<Execution>(`/projects/${projectId}/sandbox`, { method: 'POST', body: body({ path: activePath }) });
          setRun(result); await qc.invalidateQueries({ queryKey: ['executions', projectId] });
        }); }}><Play size={13}/> Run file</button>
        <button disabled={!canWrite || !!action || dirty || (!htmlPath && preview?.status !== 'running')} title={dirty ? 'Save your edits before previewing' : 'Preview an HTML project'} onClick={() => { setTab('preview'); perform('preview', async () => {
          if (preview?.status === 'running') await refreshPreview();
          else {
            const result = await api<Execution>(`/projects/${projectId}/preview`, { method: 'POST', body: body({ path: htmlPath }) });
            setPreview(result); if (result.status === 'failed') setError(result.output);
          }
          await qc.invalidateQueries({ queryKey: ['executions', projectId] });
        }); }}><Monitor size={13}/> Live preview</button>
        <button className="icon-button" aria-label={expanded ? 'Collapse execution panel' : 'Expand execution panel'} onClick={() => setExpanded(!expanded)}>{expanded ? <ChevronDown size={15}/> : <ChevronUp size={15}/>}</button>
      </div>
    </div>
    {expanded && <>
      {error && <div className="execution-error" role="alert">{error}</div>}
      {action && <div className="execution-progress" role="status"><LoaderCircle size={14} className="spin"/>{action === 'run' ? 'Running in an isolated sandbox…' : action === 'stop' ? 'Stopping preview…' : action === 'refresh' ? 'Syncing saved changes…' : 'Preparing preview…'}</div>}
      {tab === 'output' ? <div className="execution-output">
        {run ? <><div className="execution-result"><span>{run.path}</span><span className={run.status === 'completed' ? 'mint' : 'error'}>{run.exit_code !== null ? `Exit ${run.exit_code}` : run.status}</span></div><pre aria-label="Program output">{run.output || 'Program completed without output.'}</pre></> : <div className="execution-empty"><Terminal size={22}/><p>Open a Python, JavaScript, or TypeScript file and choose Run file.</p><small>25-second limit · 64 KB output · network blocked</small></div>}
      </div> : preview?.status === 'running' && preview.preview_url ? <>
        <div className="preview-toolbar"><span>Refreshes on save · {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')} left</span><div>
          <button className="icon-button" disabled={!!action} title="Refresh preview" onClick={() => perform('refresh', refreshPreview)}><RefreshCw size={14}/></button>
          <a className="button icon-button" href={preview.preview_url} target="_blank" rel="noopener noreferrer" title="Open preview in a new tab"><ExternalLink size={14}/></a>
          <button disabled={!!action || !canWrite} onClick={() => perform('stop', async () => { setPreview(await api<Execution>(`/executions/${preview.id}`, { method: 'DELETE' })); await qc.invalidateQueries({ queryKey: ['executions', projectId] }); })}><Square size={12}/> Stop</button>
        </div></div>
        <iframe title="Project live preview" src={preview.preview_url} sandbox="allow-scripts" referrerPolicy="no-referrer" className="live-preview-frame"/>
      </> : <div className="execution-empty"><Monitor size={24}/><p>{preview?.status === 'expired' ? 'Preview expired. Start it again to continue.' : preview?.status === 'stopped' ? 'Preview stopped.' : 'Open an HTML file and choose Live preview.'}</p><small>HTML, CSS and JavaScript · relative assets · five-minute sessions</small></div>}
    </>}
  </section>;
}
