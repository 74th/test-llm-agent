"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { CopilotChatConfigurationProvider, UseAgentUpdate, useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import type { Message } from "@ag-ui/core";

type StoredMessage = { id: string; role: string; content: unknown };
type Thread = { id: string; title: string; updatedAt: string; lastRunStatus: string; messages?: StoredMessage[] };
const API = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";

export default function Home() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    const items: Thread[] = await fetch(`${API}/threads`).then(r => r.json());
    setThreads(items);
    setActive(current => current ?? localStorage.getItem("activeThread") ?? items[0]?.id ?? null);
  }, []);
  const create = async () => {
    const thread: Thread = await fetch(`${API}/threads`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" }).then(r => r.json());
    setThreads(items => [thread, ...items]); select(thread.id);
  };
  const select = (id: string) => { localStorage.setItem("activeThread", id); setActive(id); };
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!active && threads.length === 0) void create(); }, [active, threads.length]);
  return <main><aside><h1>Claude PoC</h1><button className="new" onClick={create}>＋ 新しいセッション</button><nav>{threads.map(t => <button key={t.id} className={t.id === active ? "selected" : ""} onClick={() => select(t.id)}><b>{t.title}</b><small>{new Date(t.updatedAt).toLocaleString("ja-JP")} · {t.lastRunStatus}</small></button>)}</nav></aside><section>{active ? <Chat key={active} threadId={active} onComplete={refresh} /> : <p>セッションを準備中…</p>}</section></main>;
}

function Chat(props: { threadId: string; onComplete: () => Promise<void> }) {
  return <CopilotChatConfigurationProvider agentId="default" threadId={props.threadId}><ChatInner {...props} /></CopilotChatConfigurationProvider>;
}

function ChatInner({ threadId, onComplete }: { threadId: string; onComplete: () => Promise<void> }) {
  const { agent } = useAgent({ agentId: "default", updates: [UseAgentUpdate.OnMessagesChanged, UseAgentUpdate.OnRunStatusChanged] });
  const { copilotkit } = useCopilotKit();
  const [input, setInput] = useState(""); const [error, setError] = useState<string | null>(null);
  useEffect(() => { let live = true; fetch(`${API}/threads/${threadId}`).then(r => r.json()).then((thread: Thread) => { if (!live) return; const messages = thread.messages ?? []; agent.setMessages(messages.flatMap<Message>(m => {
    if ((m.role === "user" || m.role === "assistant") && typeof m.content === "string") return [{ id: m.id, role: m.role, content: m.content }];
    if (m.role === "tool" && typeof m.content === "object" && m.content !== null) {
      const result = m.content as { type?: string; toolCallId?: string; content?: unknown };
      if (result.type === "tool_result" && result.toolCallId) return [{ id: m.id, role: "tool" as const, toolCallId: result.toolCallId, content: typeof result.content === "string" ? result.content : JSON.stringify(result.content) }];
    }
    return [];
  })); }); return () => { live = false; agent.abortRun(); }; }, [agent, threadId]);
  const submit = async (e: FormEvent) => { e.preventDefault(); const text = input.trim(); if (!text || agent.isRunning) return; setInput(""); setError(null); agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text }); try { await copilotkit.runAgent({ agent }); await onComplete(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } };
  const visible = agent.messages;
  return <div className="chat"><header><strong>セッション: {threadId}</strong><span className="run-status" role="status" aria-live="polite">{agent.isRunning ? <><i className="spinner" aria-hidden="true" />実行中</> : "○ 待機中"}</span></header><div className="messages">{visible.map((m: any) => <article key={m.id} className={m.role}><label>{m.role}</label><div>{typeof m.content === "string" ? m.content : JSON.stringify(m.content)}</div></article>)}{agent.isRunning && <div className="working" role="status"><i className="spinner" aria-hidden="true" /><span>Claudeが処理しています…</span></div>}{error && <p className="error">{error}</p>}</div><form onSubmit={submit}><textarea value={input} onChange={e => setInput(e.target.value)} placeholder="東京の天気を教えて（⌘/Ctrl+Enterで送信）" onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} /><button disabled={!input.trim() || agent.isRunning}>送信</button>{agent.isRunning && <button type="button" className="stop" onClick={() => agent.abortRun()}>停止</button>}</form></div>;
}
