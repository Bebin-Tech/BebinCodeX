import type { Metadata } from 'next';
import './globals.css';
import { Providers } from '@/components/providers';
export const metadata: Metadata = { title: 'BebincodeX — AI coding workspace', description: 'A connected coding workspace with an AI agent, reviewable changes, and a real code editor.' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body><Providers>{children}</Providers></body></html>;
}
