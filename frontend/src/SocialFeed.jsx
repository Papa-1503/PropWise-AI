import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";

const API_BASE = "/api";

const CATEGORY_STYLE = {
  announcement: "bg-blue-50 text-blue-700 border-blue-200",
  shoutout: "bg-amber-50 text-amber-700 border-amber-200",
  general: "bg-slate-50 text-slate-600 border-slate-200",
};
const CATEGORY_LABEL = { announcement: "📢 Announcement", shoutout: "🎉 Shoutout", general: "Post" };

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function Composer({ onPosted, colleagues, authFetch }) {
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("general");
  const [taggedUserId, setTaggedUserId] = useState("");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState(null);

  async function submit() {
    if (!content.trim()) return;
    if (category === "shoutout" && !taggedUserId) {
      setError("Pick who this shoutout is for.");
      return;
    }
    setPosting(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/social/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: content.trim(),
          category,
          taggedUserId: category === "shoutout" ? taggedUserId : undefined,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Couldn't post");
      setContent("");
      setTaggedUserId("");
      setCategory("general");
      onPosted();
    } catch (err) {
      setError(err.message);
    } finally {
      setPosting(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Share an update, announcement, or give a shoutout…"
        rows={3}
        className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 resize-none"
      />
      <div className="flex items-center justify-between mt-2 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5"
          >
            <option value="general">General post</option>
            <option value="announcement">📢 Announcement</option>
            <option value="shoutout">🎉 Shoutout</option>
          </select>
          {category === "shoutout" && (
            <select
              value={taggedUserId}
              onChange={(e) => setTaggedUserId(e.target.value)}
              className="text-xs border border-slate-200 rounded-lg px-2 py-1.5"
            >
              <option value="">Who's it for?</option>
              {colleagues.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={submit}
          disabled={posting || !content.trim()}
          className="text-xs font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
        >
          {posting ? "Posting…" : "Post"}
        </button>
      </div>
      {error && <p className="text-xs text-rose-600 mt-2">{error}</p>}
    </div>
  );
}

function CommentThread({ postId, authFetch, onCommentAdded }) {
  const [comments, setComments] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    const res = await authFetch(`${API_BASE}/social/posts/${postId}/comments`);
    if (res.ok) {
      setComments((await res.json()).comments);
      setLoaded(true);
    }
  }, [postId, authFetch]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit() {
    if (!input.trim()) return;
    setSending(true);
    try {
      const res = await authFetch(`${API_BASE}/social/posts/${postId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: input.trim() }),
      });
      if (res.ok) {
        setInput("");
        load();
        onCommentAdded();
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      {loaded && comments.length > 0 && (
        <div className="space-y-2 mb-2">
          {comments.map((c, i) => (
            <div key={i} className="text-xs bg-slate-50 rounded-lg px-3 py-2">
              <span className="font-semibold">{c.authorName}</span>{" "}
              <span className="text-slate-400">{timeAgo(c.createdAt)}</span>
              <p className="text-slate-700 mt-0.5">{c.content}</p>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Write a comment…"
          className="flex-1 text-xs border border-slate-200 rounded-lg px-2.5 py-1.5"
        />
        <button
          onClick={submit}
          disabled={sending}
          className="text-xs font-semibold bg-slate-100 px-3 py-1.5 rounded-lg"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function PostCard({ post, authFetch, onUpdated }) {
  const [showComments, setShowComments] = useState(false);
  const [reacting, setReacting] = useState(false);

  async function toggleReaction() {
    setReacting(true);
    try {
      const res = await authFetch(`${API_BASE}/social/posts/${post.id}/react`, { method: "POST" });
      if (res.ok) onUpdated(await res.json());
    } finally {
      setReacting(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 mb-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-slate-900 text-white text-xs font-semibold flex items-center justify-center">
            {post.authorName?.[0] || "?"}
          </div>
          <div>
            <div className="text-sm font-semibold">{post.authorName}</div>
            <div className="text-[10px] text-slate-400">{timeAgo(post.createdAt)}</div>
          </div>
        </div>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${CATEGORY_STYLE[post.category]}`}>
          {CATEGORY_LABEL[post.category]}
        </span>
      </div>

      {post.category === "shoutout" && post.taggedUserName && (
        <p className="text-xs text-amber-700 mb-1.5">🎉 Shoutout to <b>{post.taggedUserName}</b></p>
      )}

      <p className="text-sm text-slate-800 whitespace-pre-wrap">{post.content}</p>

      <div className="flex items-center gap-4 mt-3 pt-2">
        <button
          onClick={toggleReaction}
          disabled={reacting}
          className={`text-xs flex items-center gap-1 ${post.reactedByMe ? "text-indigo-600 font-semibold" : "text-slate-500"}`}
        >
          {post.reactedByMe ? "👍" : "🤍"} {post.reactionCount > 0 ? post.reactionCount : "Like"}
        </button>
        <button
          onClick={() => setShowComments((s) => !s)}
          className="text-xs text-slate-500"
        >
          💬 {post.commentCount > 0 ? `${post.commentCount} comment${post.commentCount !== 1 ? "s" : ""}` : "Comment"}
        </button>
      </div>

      {showComments && (
        <CommentThread
          postId={post.id}
          authFetch={authFetch}
          onCommentAdded={() => onUpdated({ ...post, commentCount: post.commentCount + 1 })}
        />
      )}
    </div>
  );
}

/**
 * SocialFeed
 *
 * Internal staff engagement feed — Workvivo-style: announcements, general
 * posts, and peer recognition ("shoutouts"), with reactions and comments.
 * Staff-only, matching the backend (routers/social.py requires staff).
 */
export default function SocialFeed() {
  const [posts, setPosts] = useState([]);
  const [colleagues, setColleagues] = useState([]);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  const fetchPosts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/social/posts`);
      if (res.ok) setPosts((await res.json()).posts);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  const fetchColleagues = useCallback(async () => {
    const res = await authFetch(`${API_BASE}/social/posts/colleagues`);
    if (res.ok) setColleagues((await res.json()).colleagues);
  }, [authFetch]);

  useEffect(() => {
    fetchPosts();
    fetchColleagues();
  }, [fetchPosts, fetchColleagues]);

  function handlePostUpdated(updated) {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-lg font-semibold mb-1">Team Feed</h2>
      <p className="text-xs text-slate-500 mb-4">Announcements, updates, and shoutouts for the team</p>

      <Composer onPosted={fetchPosts} colleagues={colleagues} authFetch={authFetch} />

      {loading && <p className="text-sm text-slate-400 text-center py-8">Loading feed…</p>}
      {!loading && posts.length === 0 && (
        <p className="text-sm text-slate-400 text-center py-8">No posts yet — be the first to share something.</p>
      )}
      {posts.map((post) => (
        <PostCard key={post.id} post={post} authFetch={authFetch} onUpdated={handlePostUpdated} />
      ))}
    </div>
  );
}
