export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...init, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...init.headers } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'Request failed. Check the supplied fields.');
  return data as T;
}
export const body = (value: unknown) => JSON.stringify(value);
export interface User { id: string; name: string; email: string }
export interface Org { id: string; name: string; role: string; local_only: boolean; monthly_token_limit: number }
export interface Project { id: string; org_id: string; name: string; description: string; revision: number; created_at: string }
export interface SourceFile { id: string; path: string; content: string; version: number }
export interface Connection { id: string; provider: string; label: string }
export interface Run { id: string; prompt: string; status: string; model: string; summary: string; proposal: { path: string; content: string | null }[]; snapshot: Record<string, string>; base_revision: number; created_at: string }
