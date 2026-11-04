'use client';
import { useEffect, useState } from 'react';
import Editor, { DiffEditor, loader, type EditorProps, type DiffEditorProps } from '@monaco-editor/react';

type MonacoWindow = Window & {
  monaco?: typeof import('monaco-editor');
  MonacoEnvironment?: { getWorker: (_: string, label: string) => Worker };
};
let ready: Promise<void> | undefined;
function initialize() {
  return ready ||= new Promise<void>((resolve,reject)=>{
    const win=window as MonacoWindow;
    win.MonacoEnvironment={getWorker:(_,label)=>new Worker(`/monaco/${label==='json'?'json':label==='css'||label==='scss'||label==='less'?'css':label==='html'||label==='handlebars'||label==='razor'?'html':label==='typescript'||label==='javascript'?'ts':'editor'}.worker.js`)};
    const style=document.createElement('link');style.rel='stylesheet';style.href='/monaco/editor.css';document.head.appendChild(style);
    const script=document.createElement('script');script.src='/monaco/editor.js';
    script.onload=()=>{
      if(!win.monaco){reject(new Error('Editor did not initialize'));return;}
      win.monaco.editor.defineTheme('bebincodex-dark', {
        base:'vs-dark', inherit:true, rules:[],
        colors:{
          'editor.background':'#0b1020',
          'editor.foreground':'#edf2fa',
          'editor.lineHighlightBackground':'#111b30',
          'editorLineNumber.foreground':'#657796',
          'editorLineNumber.activeForeground':'#abc7ff',
          'editor.selectionBackground':'#264572',
          'editorCursor.foreground':'#82aaff',
          'editorWidget.background':'#17243b',
          'editorWidget.border':'#2a354a',
        },
      });
      loader.config({monaco:win.monaco});resolve();
    };
    script.onerror=()=>reject(new Error('Unable to load local editor assets'));
    document.head.appendChild(script);
  });
}
function useEditorReady(){
  const [state,setState]=useState<'loading'|'ready'|'error'>('loading');
  useEffect(()=>{let active=true;initialize().then(()=>{if(active)setState('ready');}).catch(()=>{if(active)setState('error');});return()=>{active=false;};},[]);
  return state;
}
export function CodeEditor(props:EditorProps){const state=useEditorReady();return state==='ready'?<Editor {...props} theme={props.theme==='vs-dark'?'bebincodex-dark':props.theme}/>:<div className="empty fill">{state==='error'?'Editor could not load. Refresh to retry.':'Loading editor…'}</div>;}
export function CodeDiffEditor(props:DiffEditorProps){const state=useEditorReady();return state==='ready'?<DiffEditor {...props} theme={props.theme==='vs-dark'?'bebincodex-dark':props.theme}/>:<div className="empty fill">{state==='error'?'Editor could not load. Refresh to retry.':'Loading diff…'}</div>;}
