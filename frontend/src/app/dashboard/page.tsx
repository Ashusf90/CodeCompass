"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Check,
  Clock3,
  Code2,
  ExternalLink,
  FolderGit2,
  GitBranch,
  LoaderCircle,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type User = {
  id: string;
  username: string;
  email: string | null;
};

type Repository = {
  id: string;
  name: string;
  github_url: string;
  status: "queued" | "indexing" | "ready" | "failed" | string;
  branch: string | null;
  commit_sha: string | null;
  error_message: string | null;
};

function Status({ status }: { status: string }) {
  const ready = status === "ready";
  const failed = status === "failed";
  const active = status === "indexing" || status === "queued";

  return (
    <span className={`status status-${status}`}>
      {ready ? <Check size={12} /> : failed ? <AlertCircle size={12} /> : active ? <LoaderCircle size={12} className="spin" /> : <Clock3 size={12} />}
      {status}
    </span>
  );
}

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [search, setSearch] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const meResponse = await fetch(`${API}/api/auth/me`, {
        credentials: "include",
        cache: "no-store",
      });

      if (meResponse.status === 401) {
        setAuthenticated(false);
        setUser(null);
        setRepositories([]);
        return;
      }

      if (!meResponse.ok) throw new Error("Could not verify your session.");

      const currentUser: User = await meResponse.json();
      setUser(currentUser);
      setAuthenticated(true);

      const repoResponse = await fetch(`${API}/api/repositories`, {
        credentials: "include",
        cache: "no-store",
      });

      if (!repoResponse.ok) throw new Error("Could not load your repositories.");

      setRepositories(await repoResponse.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  async function addRepository(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAdding(true);
    setError("");
    setNotice("");

    try {
      const response = await fetch(`${API}/api/repositories`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: repoUrl }),
      });

      const data = await response.json();

      if (!response.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((item: { msg?: string }) => item.msg).join(", ")
              : "Could not add this repository.",
        );
      }

      setRepoUrl("");
      setShowAdd(false);
      setNotice("Repository added. Indexing has been queued.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add repository.");
    } finally {
      setAdding(false);
    }
  }

  async function logout() {
    await fetch(`${API}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    setAuthenticated(false);
    setUser(null);
    setRepositories([]);
  }

  const filtered = repositories.filter((repo) =>
    `${repo.name} ${repo.github_url}`.toLowerCase().includes(search.toLowerCase()),
  );

  const readyCount = repositories.filter((repo) => repo.status === "ready").length;
  const activeCount = repositories.filter((repo) =>
    ["queued", "indexing"].includes(repo.status),
  ).length;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a href="/dashboard" className="brand">
          <span className="brand-mark"><Code2 size={19} strokeWidth={2.1} /></span>
          <span>CodeCompass</span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav">
          <a className="nav-item active" href="/dashboard">
            <FolderGit2 size={17} /> Repositories
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-divider" />
          <div className="sidebar-product">
            <div className="product-icon"><Activity size={15} /></div>
            <div>
              <div className="product-name">Code intelligence</div>
              <div className="product-caption">Grounded in your codebase</div>
            </div>
          </div>
          {authenticated && user && (
            <div className="user-panel">
              <div className="avatar">{user.username.slice(0, 1).toUpperCase()}</div>
              <div className="user-info">
                <div className="user-name">{user.username}</div>
                <div className="user-caption">GitHub account</div>
              </div>
              <button className="icon-button logout-button" onClick={logout} title="Sign out" aria-label="Sign out">
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-separator">/</span>
            <strong>Repositories</strong>
          </div>
          <div className="topbar-right">
            <span className="connection-indicator"><span /> API workspace</span>
            {authenticated && (
              <button className="icon-button" onClick={() => void loadDashboard()} title="Refresh">
                <RefreshCw size={16} />
              </button>
            )}
          </div>
        </header>

        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">DEVELOPER WORKSPACE</div>
              <h1>Repositories</h1>
              <p className="page-description">
                Explore, index, and ask questions about your codebases.
              </p>
            </div>
            {authenticated && (
              <button className="primary-button" onClick={() => { setShowAdd(!showAdd); setError(""); }}>
                <Plus size={16} /> Add repository
              </button>
            )}
          </div>

          {authenticated && (
            <div className="overview-row">
              <div className="overview-item">
                <span className="overview-label">Repositories</span>
                <span className="overview-value">{repositories.length}</span>
              </div>
              <div className="overview-item">
                <span className="overview-label">Indexed</span>
                <span className="overview-value">{readyCount}</span>
              </div>
              <div className="overview-item">
                <span className="overview-label">In progress</span>
                <span className="overview-value">{activeCount}</span>
              </div>
            </div>
          )}

          {showAdd && authenticated && (
            <form className="add-panel" onSubmit={addRepository}>
              <div className="add-panel-heading">
                <div>
                  <h2>Connect a repository</h2>
                  <p>Enter the HTTPS URL of a public GitHub repository.</p>
                </div>
                <button type="button" className="icon-button" onClick={() => setShowAdd(false)} aria-label="Close">
                  <X size={17} />
                </button>
              </div>
              <label htmlFor="repo-url">GitHub repository URL</label>
              <div className="input-row">
                <div className="url-input-wrap">
                  <GitBranch size={16} />
                  <input
                    id="repo-url"
                    type="url"
                    placeholder="https://github.com/owner/repository"
                    value={repoUrl}
                    onChange={(event) => setRepoUrl(event.target.value)}
                    required
                  />
                </div>
                <button className="primary-button" type="submit" disabled={adding}>
                  {adding ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}
                  {adding ? "Adding..." : "Connect"}
                </button>
              </div>
              <p className="form-hint">Only public repositories are supported in this version.</p>
            </form>
          )}

          {error && (
            <div className="feedback feedback-error">
              <AlertCircle size={16} /> <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss"><X size={15} /></button>
            </div>
          )}
          {notice && (
            <div className="feedback feedback-success">
              <Check size={16} /> <span>{notice}</span>
              <button onClick={() => setNotice("")} aria-label="Dismiss"><X size={15} /></button>
            </div>
          )}

          <div className="section-heading">
            <div>
              <h2>Your repositories</h2>
              <p>Connected GitHub projects</p>
            </div>
            {authenticated && repositories.length > 0 && (
              <div className="search-box">
                <Search size={15} />
                <input
                  aria-label="Search repositories"
                  placeholder="Find a repository"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
            )}
          </div>

          {loading ? (
            <div className="loading-state">
              <LoaderCircle className="spin" size={22} />
              <span>Loading workspace...</span>
            </div>
          ) : !authenticated ? (
            <div className="welcome-panel">
              <div className="welcome-icon"><GitBranch size={25} /></div>
              <h2>Sign in to your workspace</h2>
              <p>Connect your GitHub account to add repositories and start asking questions about your code.</p>
              <a className="primary-button sign-in-button" href={`${API}/api/auth/github/login`}>
                <GitBranch size={17} /> Continue with GitHub <ArrowUpRight size={15} />
              </a>
              <span className="welcome-footnote">Authentication handled securely by GitHub OAuth.</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><FolderGit2 size={22} /></div>
              <h3>{repositories.length === 0 ? "No repositories connected" : "No matching repositories"}</h3>
              <p>
                {repositories.length === 0
                  ? "Connect a public GitHub repository to begin indexing its code."
                  : "Try a different repository name or URL."}
              </p>
              {repositories.length === 0 && (
                <button className="secondary-button" onClick={() => setShowAdd(true)}>
                  <Plus size={15} /> Connect your first repository
                </button>
              )}
            </div>
          ) : (
            <div className="repository-list">
              {filtered.map((repo) => (
                <article className="repository-card" key={repo.id}>
                  <div className="repo-icon"><Code2 size={19} /></div>
                  <div className="repo-main">
                    <div className="repo-title-row">
                      <h3>{repo.name}</h3>
                      <Status status={repo.status} />
                    </div>
                    <a className="repo-url" href={repo.github_url} target="_blank" rel="noreferrer">
                      {repo.github_url.replace("https://github.com/", "")}
                      <ExternalLink size={12} />
                    </a>
                    <div className="repo-meta">
                      {repo.branch && <span><GitBranch size={13} /> {repo.branch}</span>}
                      {repo.commit_sha && <span className="commit-sha">Commit {repo.commit_sha.slice(0, 7)}</span>}
                    </div>
                    {repo.error_message && (
                      <div className="repo-error"><AlertCircle size={13} /> {repo.error_message}</div>
                    )}
                  </div>
                  <div className="repo-action">
                    {repo.status === "ready" ? (
                      <Link
                        href={`/repositories/${repo.id}/chat`}
                        className="workspace-link"
                      >
                        Open workspace <ArrowUpRight size={14} />
                      </Link>
                    ) : (
                      <span className="processing-label">
                        {repo.status === "failed" ? "Needs attention" : "Processing"}
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}

          <footer className="page-footer">
            <span>CodeCompass <span className="footer-separator">·</span> Repository intelligence</span>
            <span>Built for developers</span>
          </footer>
        </div>
      </section>
    </main>
  );
}
