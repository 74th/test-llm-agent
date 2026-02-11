import { useState, useEffect, useRef } from 'react'
import './App.css'

interface BaseMessage {
  id: string
}

interface UserMessage extends BaseMessage {
  type: 'user'
  content: string
}

interface TextMessage extends BaseMessage {
  type: 'text'
  content: string
}

interface ToolCallMessage extends BaseMessage {
  type: 'tool_call'
  tool_name: string
  args: Record<string, unknown>
}

interface ToolResultMessage extends BaseMessage {
  type: 'tool_result'
  tool_name: string
  result: unknown
}

interface SystemMessage extends BaseMessage {
  type: 'system'
  content: string
}

type Message = UserMessage | TextMessage | ToolCallMessage | ToolResultMessage | SystemMessage

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    connectWebSocket()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const connectWebSocket = () => {
    const ws = new WebSocket('ws://192.168.1.179:8000/ws')

    ws.onopen = () => {
      console.log('WebSocket connected')
      setIsConnected(true)
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        type: 'system',
        content: '接続しました'
      }])
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'text') {
        setMessages(prev => [...prev, {
          id: Date.now().toString() + Math.random(),
          type: 'text',
          content: data.data.content
        }])
      } else if (data.type === 'tool_call') {
        setMessages(prev => [...prev, {
          id: Date.now().toString() + Math.random(),
          type: 'tool_call',
          tool_name: data.data.tool_name,
          args: data.data.args
        }])
      } else if (data.type === 'tool_result') {
        setMessages(prev => [...prev, {
          id: Date.now().toString() + Math.random(),
          type: 'tool_result',
          tool_name: data.data.tool_name,
          result: data.data.result
        }])
      } else if (data.type === 'complete') {
        setIsLoading(false)
      } else if (data.type === 'error') {
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          type: 'system',
          content: `エラー: ${data.message}`
        }])
        setIsLoading(false)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        type: 'system',
        content: 'WebSocketエラーが発生しました'
      }])
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setIsConnected(false)
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        type: 'system',
        content: '接続が切断されました'
      }])

      // 再接続を試みる
      setTimeout(() => {
        if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
          connectWebSocket()
        }
      }, 3000)
    }

    wsRef.current = ws
  }

  const sendMessage = () => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || isLoading) {
      return
    }

    const userMessage: UserMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: input
    }

    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)

    wsRef.current.send(JSON.stringify({
      message: input
    }))

    setInput('')
  }

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const renderMessage = (msg: Message) => {
    if (msg.type === 'user') {
      return (
        <div key={msg.id} className="message user">
          <div className="message-role">ユーザー</div>
          <div className="message-content">{msg.content}</div>
        </div>
      )
    } else if (msg.type === 'text') {
      return (
        <div key={msg.id} className="message assistant">
          <div className="message-role">エージェント</div>
          <div className="message-content">{msg.content}</div>
        </div>
      )
    } else if (msg.type === 'tool_call') {
      return (
        <div key={msg.id} className="message tool-call">
          <div className="message-role">🔧 ツール呼び出し</div>
          <div className="message-content">
            <div className="tool-name">ツール名: <strong>{msg.tool_name}</strong></div>
            <div className="tool-args">
              引数: <pre>{JSON.stringify(msg.args, null, 2)}</pre>
            </div>
          </div>
        </div>
      )
    } else if (msg.type === 'tool_result') {
      return (
        <div key={msg.id} className="message tool-result">
          <div className="message-role">📊 ツール実行結果</div>
          <div className="message-content">
            <div className="tool-name">ツール名: <strong>{msg.tool_name}</strong></div>
            <div className="tool-result-content">
              <details>
                <summary>結果を表示</summary>
                <pre>{JSON.stringify(msg.result, null, 2)}</pre>
              </details>
            </div>
          </div>
        </div>
      )
    } else if (msg.type === 'system') {
      return (
        <div key={msg.id} className="message system">
          <div className="message-role">システム</div>
          <div className="message-content">{msg.content}</div>
        </div>
      )
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>DeepAgent WebUI</h1>
        <div className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? '接続中' : '切断中'}
        </div>
      </header>

      <div className="messages-container">
        {messages.map(msg => renderMessage(msg))}
        {isLoading && (
          <div className="message assistant loading">
            <div className="message-role">エージェント</div>
            <div className="message-content">処理中...</div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="メッセージを入力..."
          disabled={!isConnected || isLoading}
          className="input"
        />
        <button
          onClick={sendMessage}
          disabled={!isConnected || !input.trim() || isLoading}
          className="send-button"
        >
          送信
        </button>
      </div>
    </div>
  )
}

export default App
