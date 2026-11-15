"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  ArrowUp,
  FileCode2,
  FileText,
  FolderGit2,
  LoaderCircle,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  X,
} from "lucide-react";
import { codeToHtml } from "shiki";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Repository = {
  id: string;
  name: string;
  github_url: string;
  status: string;
  branch: string | null;
  commit_sha: string | null;
  error_message: string | null;
};

type Citation = {
  id: number;
  file_path: string;
  start_line: number;
  end_line: number;
  github_url: string;
  similarity: number;
};

type ChatSession = {
  id: string;
  repository_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
};

type SourceFile = {
  repository_id: string;
  file_path: string;
  language: string | null;
  file_type: string | null;
  content: string;
};

type Usage = {
  request_count: number;
  estimated_tokens: number;
  requests_per_minute_limit: number;
  daily_token_budget: number;
  remaining_estimated_tokens: number;
};

function CodeViewer({
  source,
  citation,
}: {
  source: SourceFile;
  citation: Citation | null;
}) {
  const [html, setHtml] = useState("");
  const [highlightError, setHighlightError] = useState(false);

  useEffect(() => {
    let active = true;

    async function highlight() {
      try {
        const language = (source.language || "text").toLowerCase();
        const aliases: Record<string, string> = {
          py: "python",
          js: "javascript",
          jsx: "jsx",
          ts: "typescript",
          tsx: "tsx",
          sh: "bash",
          yml: "yaml",
          md: "markdown",
          txt: "text",
        };

        const rendered = await codeToHtml(source.content, {
          lang: aliases[language] || language,
          theme: "github-dark",
        });

        if (active) {
          setHtml(rendered);
          setHighlightError(false);
        }
      } catch {
        if (active) {
          setHtml("");
          setHighlightError(true);
        }
      }
    }

    void highlight();
    return () => {
      active = false;
    };
  }, [source]);

  const lines = source.content.split("\n");

  return (
    <div className="source-code">
      <div className="source-code-meta">
        <span>{source.language || "Plain text"}</span>
        {citation && (
          <span>
            Lines {citation.start_line}–{citation.end_line}
          </span>
        )}
      </div>

      {html && !highlightError ? (
        <div
          className="shiki-viewer"
          dangerouslySetInnerHTML={{
            __html: html.replace(
              /<span class="line">/g,
              (match, offset, full) => {
                const before = full.slice(0, offset);
                const lineNumber = (before.match(/<span class="line">/g) || []).length + 1;
                const selected =
                  citation &&
                  lineNumber >= citation.start_line &&
                  lineNumber <= citation.end_line;

                return selected
                  ? '<span class="line citation-line">'
                  : match;
              },
            ),
          }}
        />
      ) : (
        <pre className="plain-source">
          <code>
            {lines.map((line, index) => {
              const lineNumber = index + 1;
              const selected =
                citation &&
                lineNumber >= citation.start_line &&
                lineNumber <= citation.end_line;

              return (
                <span
                  className={`plain-code-line ${selected ? "citation-line" : ""}`}
                  key={lineNumber}
                >
                  <span className="line-number">{lineNumber}</span>
                  {line || " "}
                </span>
              );
            })}
          </code>
        </pre>
      )}
    </div>
  );
}

export default function RepositoryChatClient({ repositoryId }: { repositoryId: string }) {
  const router = useRouter();

  const [repository, setRepository] = useState<Repository | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [source, setSource] = useState<SourceFile | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<"history" | "sources" | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadSessions = useCallback(async () => {
    const response = await fetch(
      `${API}/api/repositories/${repositoryId}/chat/sessions`,
      { credentials: "include", cache: "no-store" },
    );

    if (!response.ok) throw new Error("Could not load chat history.");
    setSessions(await response.json());
  }, [repositoryId]);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [meResponse, repoResponse, sessionsResponse, usageResponse] =
        await Promise.all([
          fetch(`${API}/api/auth/me`, {
            credentials: "include",
            cache: "no-store",
          }),
          fetch(`${API}/api/repositories/${repositoryId}`, {
            credentials: "include",
            cache: "no-store",
          }),
          fetch(`${API}/api/repositories/${repositoryId}/chat/sessions`, {
            credentials: "include",
            cache: "no-store",
          }),
          fetch(`${API}/api/usage/me`, {
            credentials: "include",
            cache: "no-store",
          }),
        ]);

      if (meResponse.status === 401) {
        router.replace("/dashboard");
        return;
      }

      if (!repoResponse.ok) {
        throw new Error(
          repoResponse.status === 404
            ? "Repository not found or you do not have access."
            : "Could not load this repository.",
        );
      }

      if (!sessionsResponse.ok) {
        throw new Error("Could not load chat history.");
      }

      setRepository(await repoResponse.json());
      setSessions(await sessionsResponse.json());

      if (usageResponse.ok) {
        setUsage(await usageResponse.json());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace could not load.");
    } finally {
      setLoading(false);
    }
  }, [repositoryId, router]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function openSession(sessionId: string) {
    setError("");
    setSelectedSession(sessionId);
    setSelectedCitation(null);
    setSource(null);

    try {
      const response = await fetch(
        `${API}/api/repositories/${repositoryId}/chat/sessions/${sessionId}/messages`,
        { credentials: "include", cache: "no-store" },
      );

      if (!response.ok) throw new Error("Could not load this conversation.");
      setMessages(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load conversation.");
    }
  }

  function startNewChat() {
    setSelectedSession(null);
    setMessages([]);
    setQuestion("");
    setSelectedCitation(null);
    setSource(null);
    setError("");
    textareaRef.current?.focus();
  }

  async function openCitation(citation: Citation) {
    setSelectedCitation(citation);
    setSourceLoading(true);
    setMobilePanel("sources");

    try {
      const response = await fetch(
        `${API}/api/repositories/${repositoryId}/files?file_path=${encodeURIComponent(citation.file_path)}`,
        { credentials: "include", cache: "no-store" },
      );

      if (!response.ok) throw new Error("Could not load this source file.");
      setSource(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load source file.");
      setSource(null);
    } finally {
      setSourceLoading(false);
    }
  }

  async function sendMessage(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    const query = question.trim();
    if (!query || sending) return;

    setError("");
    setSending(true);
    setQuestion("");

    const temporaryUserMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      session_id: selectedSession || "",
      role: "user",
      content: query,
      citations: null,
      created_at: new Date().toISOString(),
    };

    const temporaryAssistantMessage: ChatMessage = {
      id: `assistant-${Date.now()}`,
      session_id: selectedSession || "",
      role: "assistant",
      content: "",
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((current) => [
      ...current,
      temporaryUserMessage,
      temporaryAssistantMessage,
    ]);

    let assistantText = "";
    let citations: Citation[] = [];
    let completedSessionId: string | null = selectedSession;
    let streamError = "";

    try {
      const response = await fetch(
        `${API}/api/repositories/${repositoryId}/chat/stream`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            limit: 5,
            rerank: true,
            exclude_tests: false,
            ...(selectedSession ? { session_id: selectedSession } : {}),
          }),
        },
      );

      if (!response.ok) {
        let message = "The chat request failed.";
        try {
          const data = await response.json();
          message = data.detail || message;
        } catch {
          // Keep the default error message.
        }
        throw new Error(message);
      }

      if (!response.body) throw new Error("Streaming is not supported by this response.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      function updateAssistant() {
        setMessages((current) =>
          current.map((message) =>
            message.id === temporaryAssistantMessage.id
              ? { ...message, content: assistantText, citations }
              : message,
          ),
        );
      }

      function processEvent(block: string) {
        let eventName = "message";
        const dataLines: string[] = [];

        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          }
        }

        if (!dataLines.length) return;

        let data: Record<string, unknown>;
        try {
          data = JSON.parse(dataLines.join("\n"));
        } catch {
          return;
        }

        if (eventName === "token" && typeof data.content === "string") {
          assistantText += data.content;
          updateAssistant();
        } else if (eventName === "answer" && typeof data.content === "string") {
          assistantText = data.content;
          updateAssistant();
        } else if (eventName === "citations" && Array.isArray(data.sources)) {
          citations = data.sources as Citation[];
          updateAssistant();
          if (citations.length > 0) {
            void openCitation(citations[0]);
          }
        } else if (eventName === "error" && typeof data.message === "string") {
          streamError = data.message;
        } else if (eventName === "done") {
          if (typeof data.session_id === "string") {
            completedSessionId = data.session_id;
          }
        }
      }

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";

        for (const block of blocks) {
          processEvent(block);
        }

        if (done) break;
      }

      if (buffer.trim()) processEvent(buffer);

      if (completedSessionId) {
        setSelectedSession(completedSessionId);
      }

      if (streamError) setError(streamError);

      if (!assistantText && !streamError) {
        assistantText = "The response finished without any text.";
      }

      updateAssistant();
      await loadSessions();

      if (completedSessionId) {
        const historyResponse = await fetch(
          `${API}/api/repositories/${repositoryId}/chat/sessions/${completedSessionId}/messages`,
          { credentials: "include", cache: "no-store" },
        );

        if (historyResponse.ok) {
          setMessages(await historyResponse.json());
        }
      }

      const usageResponse = await fetch(`${API}/api/usage/me`, {
        credentials: "include",
        cache: "no-store",
      });

      if (usageResponse.ok) setUsage(await usageResponse.json());
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Something went wrong.";

      setError(message);
      setMessages((current) =>
        current.map((item) =>
          item.id === temporaryAssistantMessage.id
            ? {
                ...item,
                content: assistantText || "I couldn't complete this request.",
                citations,
              }
            : item,
        ),
      );
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }

  function handleComposerKey(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  if (loading) {
    return (
      <main className="workspace-loading">
        <LoaderCircle className="spin" size={22} />
        <span>Opening repository workspace</span>
      </main>
    );
  }

  if (!repository) {
    return (
      <main className="workspace-loading">
        <p>{error || "Repository unavailable."}</p>
        <Link href="/dashboard">Return to dashboard</Link>
      </main>
    );
  }

  return (
    <main className="workspace-shell">
      <header className="workspace-topbar">
        <div className="workspace-brand">
          <Link href="/dashboard" className="workspace-back" aria-label="Back to dashboard">
            <ArrowLeft size={17} />
          </Link>
          <div className="workspace-brand-mark">
            <FolderGit2 size={17} />
          </div>
          <div className="workspace-repo-heading">
            <strong>{repository.name}</strong>
            <span>
              {repository.branch || "Default branch"} ·{" "}
              {repository.status === "ready" ? "Indexed repository" : repository.status}
            </span>
          </div>
        </div>

        <div className="workspace-top-actions">
          {usage && (
            <span className="usage-indicator">
              {usage.remaining_estimated_tokens.toLocaleString()} tokens remaining today
            </span>
          )}
          <a
            href={repository.github_url}
            target="_blank"
            rel="noreferrer"
            className="github-repo-link"
          >
            View on GitHub
          </a>
        </div>
      </header>

      <div className="workspace-layout">
        <aside className={`workspace-history ${mobilePanel === "history" ? "mobile-open" : ""}`}>
          <div className="panel-heading">
            <span>CONVERSATIONS</span>
            <button
              className="icon-button"
              onClick={() => setMobilePanel(null)}
              aria-label="Close history"
            >
              <X size={16} />
            </button>
          </div>

          <button className="new-chat-button" onClick={startNewChat}>
            <Plus size={15} />
            New conversation
          </button>

          <div className="history-list">
            {sessions.length === 0 ? (
              <p className="empty-history">Your conversations will appear here.</p>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  className={`history-item ${selectedSession === session.id ? "active" : ""}`}
                  onClick={() => {
                    void openSession(session.id);
                    setMobilePanel(null);
                  }}
                >
                  <MessageSquare size={15} />
                  <span>{session.title}</span>
                </button>
              ))
            )}
          </div>

          <div className="history-footer">
            <span>{sessions.length} conversations</span>
            <button
              className="icon-button"
              onClick={() => void loadSessions()}
              aria-label="Refresh conversations"
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </aside>

        <section className="workspace-chat">
          <div className="mobile-workspace-actions">
            <button onClick={() => setMobilePanel("history")}>
              <MessageSquare size={15} /> History
            </button>
            <button onClick={() => setMobilePanel("sources")}>
              <FileCode2 size={15} /> Sources
            </button>
          </div>

          <div className="chat-scroll-area">
            {messages.length === 0 ? (
              <div className="chat-welcome">
                <div className="welcome-icon">
                  <FileCode2 size={24} />
                </div>
                <h1>Understand your codebase.</h1>
                <p>
                  Ask questions about {repository.name}. Answers are grounded in
                  indexed repository files and include source citations.
                </p>

                <div className="suggested-prompts">
                  {[
                    "Explain the overall architecture of this project.",
                    "Where is the application entry point?",
                    "How does authentication work?",
                    "Trace the main request flow.",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => {
                        setQuestion(prompt);
                        textareaRef.current?.focus();
                      }}
                    >
                      <span>{prompt}</span>
                      <ArrowUp size={14} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message) => (
                  <article
                    className={`chat-message ${message.role}`}
                    key={message.id}
                  >
                    <div className="message-avatar">
                      {message.role === "user" ? "You" : <FileCode2 size={16} />}
                    </div>
                    <div className="message-body">
                      <div className="message-author">
                        {message.role === "user" ? "You" : "CodeCompass"}
                      </div>

                      {message.content ? (
                        <div className="markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      ) : sending && message.role === "assistant" ? (
                        <div className="thinking-indicator">
                          <span />
                          <span />
                          <span />
                        </div>
                      ) : null}

                      {message.role === "assistant" &&
                        message.citations &&
                        message.citations.length > 0 && (
                          <div className="message-citations">
                            <div className="citation-heading">SOURCES</div>
                            {message.citations.map((citation) => (
                              <button
                                key={`${message.id}-${citation.id}`}
                                className="citation-chip"
                                onClick={() => void openCitation(citation)}
                              >
                                <FileCode2 size={13} />
                                <span>{citation.file_path}</span>
                                <small>
                                  L{citation.start_line}–{citation.end_line}
                                </small>
                              </button>
                            ))}
                          </div>
                        )}
                    </div>
                  </article>
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          {error && (
            <div className="workspace-error">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={14} />
              </button>
            </div>
          )}

          <form className="chat-composer" onSubmit={sendMessage}>
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleComposerKey}
              placeholder={`Ask anything about ${repository.name}...`}
              rows={2}
              disabled={sending}
            />
            <div className="composer-footer">
              <span>Enter to send · Shift + Enter for a new line</span>
              <button
                type="submit"
                disabled={!question.trim() || sending}
                aria-label="Send message"
              >
                {sending ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Send size={16} />
                )}
              </button>
            </div>
          </form>
        </section>

        <aside className={`workspace-sources ${mobilePanel === "sources" ? "mobile-open" : ""}`}>
          <div className="panel-heading">
            <span>SOURCE INSPECTOR</span>
            <button
              className="icon-button"
              onClick={() => setMobilePanel(null)}
              aria-label="Close source inspector"
            >
              <X size={16} />
            </button>
          </div>

          {sourceLoading ? (
            <div className="source-empty">
              <LoaderCircle size={20} className="spin" />
              <span>Loading source file</span>
            </div>
          ) : source ? (
            <div className="source-content">
              <div className="source-file-heading">
                <FileText size={15} />
                <span title={source.file_path}>{source.file_path}</span>
              </div>
              <CodeViewer source={source} citation={selectedCitation} />
              {selectedCitation && (
                <a
                  className="source-github-link"
                  href={selectedCitation.github_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open cited lines on GitHub
                </a>
              )}
            </div>
          ) : (
            <div className="source-empty">
              <FileCode2 size={23} />
              <strong>No source selected</strong>
              <span>
                Select a citation in an AI response to inspect its repository
                file and relevant lines.
              </span>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
