import { useEffect, useMemo, useRef, useState } from "react";

type Message = {
  role: "user" | "assistant" | "system";
  content: string;
};

type ConnectionState = "disconnected" | "connecting" | "connected";

const defaultWsUrl = () => {
  const { protocol, hostname } = window.location;
  const wsProtocol = protocol === "https:" ? "wss" : "ws";
  return `${wsProtocol}://${hostname}:8000/ws`;
};

export default function App() {
  const [messages, setMessages] = useState<Message[]>([{
    role: "system",
    content: "WebSocketで接続して会話できます。"
  }]);
  const [input, setInput] = useState("");
  const [wsUrl, setWsUrl] = useState(defaultWsUrl);
  const [state, setState] = useState<ConnectionState>("disconnected");
  const [streaming, setStreaming] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  const canSend = useMemo(() => state === "connected" && input.trim() && !streaming, [
    state,
    input,
    streaming,
  ]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  const connect = () => {
    if (state === "connecting" || state === "connected") return;
    setState("connecting");

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setState("connected");
      setMessages((prev) => [
        ...prev,
        { role: "system", content: "接続しました。" },
      ]);
    };

    ws.onclose = () => {
      setState("disconnected");
      setStreaming(false);
      setMessages((prev) => [
        ...prev,
        { role: "system", content: "接続が切れました。" },
      ]);
    };

    ws.onerror = () => {
      setMessages((prev) => [
        ...prev,
        { role: "system", content: "接続エラーが発生しました。" },
      ]);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { type: string; content?: string; message?: string };
        if (payload.type === "assistant_start") {
          setStreaming(true);
          setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
          return;
        }
        if (payload.type === "assistant_chunk") {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              last.content += payload.content ?? "";
            }
            return next;
          });
          return;
        }
        if (payload.type === "assistant_end") {
          setStreaming(false);
          return;
        }
        if (payload.type === "error") {
          setStreaming(false);
          setMessages((prev) => [
            ...prev,
            { role: "system", content: payload.message ?? "エラーが発生しました。" },
          ]);
          return;
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: "system", content: "不明なメッセージを受信しました。" },
        ]);
      }
    };
  };

  const disconnect = () => {
    wsRef.current?.close();
    wsRef.current = null;
  };

  const send = () => {
    if (!canSend || !wsRef.current) return;
    const trimmed = input.trim();
    wsRef.current.send(JSON.stringify({ content: trimmed }));
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>DeepAgents WebUI</h1>
          <p>FastAPI WebSocket サーバーと対話します。</p>
        </div>
        <div className={`badge ${state}`}>{state}</div>
      </header>

      <section className="panel">
        <label htmlFor="ws-url">WebSocket URL</label>
        <div className="row">
          <input
            id="ws-url"
            value={wsUrl}
            onChange={(event) => setWsUrl(event.target.value)}
            placeholder="ws://localhost:8000/ws"
          />
          <button onClick={connect} disabled={state !== "disconnected"}>
            接続
          </button>
          <button onClick={disconnect} disabled={state === "disconnected"}>
            切断
          </button>
        </div>
      </section>

      <section className="messages">
        {messages.map((message, index) => (
          <div key={index} className={`message ${message.role}`}>
            <div className="role">{message.role}</div>
            <div className="content">{message.content}</div>
          </div>
        ))}
        {streaming && <div className="typing">AIが入力中…</div>}
        <div ref={scrollAnchorRef} />
      </section>

      <section className="panel">
        <label htmlFor="user-input">メッセージ</label>
        <div className="row">
          <textarea
            id="user-input"
            rows={3}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="質問やお願いを入力してください"
          />
          <button onClick={send} disabled={!canSend}>
            送信
          </button>
        </div>
      </section>
    </div>
  );
}
