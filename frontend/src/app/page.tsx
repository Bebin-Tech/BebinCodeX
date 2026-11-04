import Link from 'next/link';
import { ArrowRight, Code2, FileCode2, GitPullRequest, Plug } from 'lucide-react';

export default function Home() {
  return <main className="landing">
    <nav className="marketing-nav">
      <Link href="/" className="brand"><span className="logo"><Code2 size={21}/></span>BebincodeX</Link>
      <div><Link href="/docs">Docs</Link><Link href="/app">Open app <ArrowRight size={15}/></Link></div>
    </nav>
    <section className="hero">
      <h1>Your next idea.<br/><em>Ready to build.</em></h1>
      <p>Write code, work with AI, and review every change in one workspace.</p>
      <div className="hero-actions"><Link className="button primary" href="/app">Start building <ArrowRight size={17}/></Link><Link className="button" href="/docs">Quick start</Link></div>
    </section>
    <section className="feature-grid" aria-label="Workspace features">
      {[
        {icon:FileCode2,title:'Your code',text:'Edit files, keep version history, and export your projects.'},
        {icon:Plug,title:'Your models',text:'Connect your preferred AI provider and choose a model.'},
        {icon:GitPullRequest,title:'Your approval',text:'Review proposed changes before applying them.'},
      ].map(({icon:Icon,title,text})=><article key={title}><Icon size={23}/><h3>{title}</h3><p>{text}</p></article>)}
    </section>
    <footer><span className="brand"><Code2 size={18}/> BebincodeX</span><Link href="/docs">Documentation <ArrowRight size={14}/></Link></footer>
  </main>;
}
