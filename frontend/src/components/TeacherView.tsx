import { useEffect, useState } from "react";
import { collection, onSnapshot, orderBy, query } from "firebase/firestore";
import { db } from "../firebase";
import type { Submission } from "../types";
import StatusBadge from "./StatusBadge";
import FeedbackPanel from "./FeedbackPanel";
import TeacherReview from "./TeacherReview";

export default function TeacherView() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);

  // Real-time listener over every student's submissions, newest first.
  useEffect(() => {
    const q = query(collection(db, "submissions"), orderBy("createdAt", "desc"));
    return onSnapshot(q, (snap) => {
      setSubmissions(
        snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<Submission, "id">) }))
      );
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <p className="text-center text-slate-500">Loading submissions…</p>;
  }
  if (submissions.length === 0) {
    return <p className="text-center text-slate-500">No submissions yet.</p>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {submissions.map((s) => (
        <article key={s.id} className="rounded-xl bg-white p-6 shadow">
          <header className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold">{s.studentEmail}</h3>
              <p className="text-xs text-slate-400">
                {s.createdAt?.toDate().toLocaleString() ?? "…"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {s.reviewStatus === "reviewed" && (
                <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                  Reviewed
                </span>
              )}
              <StatusBadge status={s.status} />
            </div>
          </header>

          {/* Teacher can always play the audio. */}
          {s.audioUrl && (
            <audio src={s.audioUrl} controls className="mt-4 w-full" />
          )}

          {s.status === "processing" && (
            <p className="mt-4 text-sm text-slate-500">Processing…</p>
          )}
          {s.status === "error" && (
            <p className="mt-4 text-sm text-red-600">
              {s.error ?? "Processing failed."}
            </p>
          )}
          {s.status === "done" && (
            <>
              <div className="mt-4">
                <FeedbackPanel submission={s} />
              </div>
              <TeacherReview submission={s} />
            </>
          )}
        </article>
      ))}
    </div>
  );
}
