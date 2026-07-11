"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CopilotChat,
  CopilotChatConfigurationProvider,
  UseAgentUpdate,
  useAgent,
  useRenderTool,
} from "@copilotkit/react-core/v2";
import type { Message } from "@ag-ui/core";
import { z } from "zod";

type StoredMessage = { id: string; role: string; content: unknown };
type Thread = {
  id: string;
  title: string;
  updatedAt: string;
  lastRunStatus: string;
  messages?: StoredMessage[];
};

const API = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";
const WEATHER_TOOL = "mcp__weather__get_today_weather";

export default function Home() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [active, setActive] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const items: Thread[] = await fetch(`${API}/threads`).then((response) => response.json());
    setThreads(items);
    setActive((current) => current ?? localStorage.getItem("activeThread") ?? items[0]?.id ?? null);
  }, []);

  const select = (id: string) => {
    localStorage.setItem("activeThread", id);
    setActive(id);
  };

  const create = async () => {
    const thread: Thread = await fetch(`${API}/threads`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    }).then((response) => response.json());
    setThreads((items) => [thread, ...items]);
    select(thread.id);
  };

  useEffect(() => void refresh(), [refresh]);
  useEffect(() => {
    if (!active && threads.length === 0) void create();
  }, [active, threads.length]);

  return (
    <main>
      <aside>
        <h1>Claude PoC</h1>
        <button className="new" onClick={create}>＋ 新しいセッション</button>
        <nav>
          {threads.map((thread) => (
            <button key={thread.id} className={thread.id === active ? "selected" : ""} onClick={() => select(thread.id)}>
              <b>{thread.title}</b>
              <small>{new Date(thread.updatedAt).toLocaleString("ja-JP")} · {thread.lastRunStatus}</small>
            </button>
          ))}
        </nav>
      </aside>
      <section>
        {active ? <Chat key={active} threadId={active} onComplete={refresh} /> : <p>セッションを準備中…</p>}
      </section>
    </main>
  );
}

function Chat({ threadId, onComplete }: { threadId: string; onComplete: () => Promise<void> }) {
  return (
    <CopilotChatConfigurationProvider agentId="default" threadId={threadId}>
      <HistoryLoader threadId={threadId} onComplete={onComplete} />
      <WeatherToolRenderer />
      <CopilotChat
        agentId="default"
        threadId={threadId}
        className="copilot-chat"
        labels={{
          chatInputPlaceholder: "メッセージを入力してください",
          welcomeMessageText: "何について話しましょうか？",
        }}
      />
    </CopilotChatConfigurationProvider>
  );
}

function HistoryLoader({ threadId, onComplete }: { threadId: string; onComplete: () => Promise<void> }) {
  const { agent } = useAgent({
    agentId: "default",
    updates: [UseAgentUpdate.OnRunStatusChanged],
  });
  const wasRunning = useRef(false);

  useEffect(() => {
    let live = true;
    fetch(`${API}/threads/${threadId}`)
      .then((response) => response.json())
      .then((thread: Thread) => {
        if (live) agent.setMessages(toAgentMessages(thread.messages ?? []));
      });
    return () => {
      live = false;
      agent.abortRun();
    };
  }, [agent, threadId]);

  useEffect(() => {
    if (wasRunning.current && !agent.isRunning) void onComplete();
    wasRunning.current = agent.isRunning;
  }, [agent.isRunning, onComplete]);

  return null;
}

function toAgentMessages(messages: StoredMessage[]): Message[] {
  return messages.flatMap<Message>((message) => {
    if ((message.role === "user" || message.role === "assistant") && typeof message.content === "string") {
      return [{ id: message.id, role: message.role, content: message.content }];
    }
    if (message.role === "assistant" && isRecord(message.content) && message.content.type === "tool_call") {
      return [{
        id: message.id,
        role: "assistant",
        toolCalls: [{
          id: String(message.content.toolCallId),
          type: "function",
          function: {
            name: String(message.content.name),
            arguments: typeof message.content.arguments === "string" ? message.content.arguments : "{}",
          },
        }],
      }];
    }
    if (message.role === "tool" && isRecord(message.content) && message.content.type === "tool_result") {
      return [{
        id: message.id,
        role: "tool",
        toolCallId: String(message.content.toolCallId),
        content: String(message.content.content ?? ""),
      }];
    }
    return [];
  });
}

function WeatherToolRenderer() {
  useRenderTool({
    name: WEATHER_TOOL,
    parameters: z.object({ city: z.string() }),
    render: ({ status, parameters, result }) => (
      <div className="weather-card">
        <div className="weather-icon" aria-hidden="true">☀️</div>
        <div>
          <strong>{status === "inProgress" ? "天気を準備中" : `${parameters.city}の天気`}</strong>
          <p>{status === "complete" ? weatherText(result) : "天気ツールを実行しています…"}</p>
        </div>
        {status !== "complete" && <i className="spinner" aria-hidden="true" />}
      </div>
    ),
  });
  return null;
}

function weatherText(result: string): string {
  try {
    const parsed: unknown = JSON.parse(result);
    if (Array.isArray(parsed)) {
      const text = parsed.find((item) => isRecord(item) && item.type === "text")?.text;
      if (typeof text === "string") return text;
    }
  } catch {
    // The tool may already have returned plain text.
  }
  return result;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
