import { useEffect, useRef, useState } from "react";
import { Send, Plus, Mic, MicOff, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SyntaxHighlighter from "react-syntax-highlighter";
import { useChatStore } from "../store/chat";
import { wsClient } from "../lib/ws";
import { formatDistanceToNow } from "date-fns";

function MessageBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? "bg-indigo-600 text-white rounded-br-sm"
            : "bg-zinc-800 text-zinc-100 rounded-bl-sm"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "");
                return match ? (
                  <SyntaxHighlighter
                    language={match[1]}
                    PreTag="div"
                    className="rounded-lg text-xs my-2"
                  >
                    {String(children).replace(/\n$/, "")}
                  </SyntaxHighlighter>
                ) : (
                  <code className="bg-zinc-700 px-1 rounded text-xs" {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}

function StreamingBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[75%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm bg-zinc-800 text-zinc-100">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        <span className="inline-block w-1.5 h-3.5 bg-indigo-400 ml-0.5 animate-pulse rounded-sm" />
      </div>
    </div>
  );
}

export default function Chat() {
  const {
    conversations,
    activeConversationId,
    messages,
    streaming,
    streamingText,
    loadConversations,
    selectConversation,
    newConversation,
    sendMessage,
    deleteConversation,
  } = useChatStore();

  const [input, setInput] = useState("");
  const [voiceActive, setVoiceActive] = useState(false);
  const [agentActivity, setAgentActivity] = useState<string | null>(null);
  const [modelUsed, setModelUsed] = useState<{ role: string; model: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    loadConversations();
    wsClient.connect();

    const unsubAgent = wsClient.on("agent_started", (data) => {
      const d = data as { agent_name: string; model?: string };
      setAgentActivity(`${d.agent_name} working…`);
    });
    const unsubDone = wsClient.on("agent_finished", () => setAgentActivity(null));
    const unsubModel = wsClient.on("model_used", (data) => {
      const d = data as { role: string; model: string };
      setModelUsed(d);
      setTimeout(() => setModelUsed(null), 4000);
    });

    return () => {
      unsubAgent();
      unsubDone();
      unsubModel();
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    await sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleVoice = () => {
    setVoiceActive((v) => !v);
    wsClient.send(voiceActive ? "push_to_talk_stop" : "push_to_talk_start", {});
  };

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col">
        <div className="p-3">
          <button
            onClick={newConversation}
            className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            <Plus size={15} />
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => selectConversation(c.id)}
              className={`group flex items-center justify-between rounded-lg px-3 py-2 text-sm cursor-pointer transition-colors ${
                c.id === activeConversationId
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/50"
              }`}
            >
              <span className="truncate flex-1">{c.title || "New conversation"}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(c.id);
                }}
                className="opacity-0 group-hover:opacity-100 ml-1 text-zinc-600 hover:text-red-400"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Main chat area */}
      <div className="flex flex-col flex-1 bg-zinc-950">
        {/* Agent activity banner */}
        {agentActivity && (
          <div className="flex items-center gap-2 px-4 py-2 bg-indigo-900/30 border-b border-indigo-700/30 text-xs text-indigo-300">
            <div className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
            {agentActivity}
          </div>
        )}
        {/* Model-used flash */}
        {modelUsed && (
          <div className="flex items-center gap-2 px-4 py-1.5 bg-zinc-800/60 border-b border-zinc-700/30 text-xs text-zinc-500">
            <span className="text-zinc-600">using</span>
            <span className="font-mono text-zinc-400">{modelUsed.model.split(":")[0]}</span>
            <span className="text-zinc-600">for</span>
            <span className="text-zinc-400">{modelUsed.role}</span>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 && !streaming && (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
              <div className="text-4xl">⚓</div>
              <p className="text-sm">Start a conversation with Captain</p>
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} role={m.role} content={m.content} />
          ))}
          {streaming && streamingText && <StreamingBubble text={streamingText} />}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-zinc-800 p-4">
          <div className="flex items-end gap-2 bg-zinc-900 rounded-xl border border-zinc-700 p-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Captain…"
              rows={1}
              className="flex-1 bg-transparent resize-none text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none px-2 py-1 max-h-32"
              style={{ minHeight: "36px" }}
            />
            <div className="flex items-center gap-1.5 pb-0.5">
              <button
                onClick={toggleVoice}
                className={`p-2 rounded-lg transition-colors ${
                  voiceActive
                    ? "bg-red-600 text-white"
                    : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
                }`}
              >
                {voiceActive ? <MicOff size={16} /> : <Mic size={16} />}
              </button>
              <button
                onClick={handleSend}
                disabled={!input.trim() || streaming}
                className="p-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white transition-colors"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
