import { useEffect, useState, type FormEvent } from "react";
import {
  addDoc,
  collection,
  onSnapshot,
  orderBy,
  query,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../firebase";
import { useAuth } from "../auth/AuthContext";
import type { Comment } from "../types";

/** Lists and adds teacher comments under submissions/{id}/comments. */
export default function CommentSection({ submissionId }: { submissionId: string }) {
  const { user } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = query(
      collection(db, "submissions", submissionId, "comments"),
      orderBy("createdAt", "asc")
    );
    return onSnapshot(q, (snap) => {
      setComments(
        snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<Comment, "id">) }))
      );
    });
  }, [submissionId]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await addDoc(collection(db, "submissions", submissionId, "comments"), {
        text: trimmed,
        authorEmail: user?.email ?? "unknown",
        createdAt: serverTimestamp(),
      });
      setText("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Comments
      </h4>

      <ul className="mt-2 space-y-2">
        {comments.map((c) => (
          <li key={c.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
            <span className="font-medium text-slate-700">{c.authorEmail}</span>
            <span className="ml-2 text-xs text-slate-400">
              {c.createdAt?.toDate().toLocaleString() ?? "…"}
            </span>
            <p className="text-slate-800">{c.text}</p>
          </li>
        ))}
        {comments.length === 0 && (
          <li className="text-sm text-slate-400">No comments yet.</li>
        )}
      </ul>

      <form onSubmit={onSubmit} className="mt-3 flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Leave feedback…"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Post
        </button>
      </form>
    </div>
  );
}
