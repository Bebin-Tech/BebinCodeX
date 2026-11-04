import Link from 'next/link';
import { ArrowLeft, ArrowRight, Code2 } from 'lucide-react';
export default function Docs() {
  return <main className="docs">
    <Link href="/" className="brand"><Code2/> BebincodeX</Link>
    <h1>Quick start</h1>
    <p className="lead">Set up your workspace and make your first change.</p>
    <ol>
      <li><h2>Create a workspace</h2><p>Sign in, then create an organization for your projects and team.</p></li>
      <li><h2>Connect your AI</h2><p>Open AI connections, choose a provider, and add your API key. Your key is stored encrypted. Discover models to check the connection.</p></li>
      <li><h2>Open a project</h2><p>Start empty, use a template, or import a ZIP of source files. Save edits with Ctrl+S. Add coding conventions to DEVPILOT.md.</p></li>
      <li><h2>Ask and review</h2><p>Select a connection and model in the editor. Describe your change, inspect the proposed diff, then apply the files you approve. File history and run checkpoints let you restore earlier work.</p></li>
    </ol>
    <div className="notice"><h2>Available today</h2><p>Editing, AI proposals, review, project history, team invitations, and token usage. Code execution, hosted previews, Git sync, collaboration, billing, and SSO are not available yet.</p></div>
    <Link href="/app" className="button primary">Open workspace <ArrowRight size={15}/></Link>
    <Link href="/" className="back-link"><ArrowLeft size={15}/> Back home</Link>
  </main>;
}
