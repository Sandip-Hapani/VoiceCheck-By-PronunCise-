import { useEffect, useMemo, useState } from "react";
import { collection, onSnapshot, query, where } from "firebase/firestore";
import { db } from "../firebase";
import { useAuth } from "../auth/AuthContext";
import { uploadRecording } from "../lib/api";
import type { Submission } from "../types";
import { useRecorder } from "./useRecorder";
import StatusBadge from "./StatusBadge";
import FeedbackPanel from "./FeedbackPanel";
import TeacherFeedback from "./TeacherFeedback";

const MAX_SECONDS = 30;

export default function StudentView() {
  const { user } = useAuth();
  const recorder = useRecorder();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);

  // Real-time listener over THIS student's own submissions.
  useEffect(() => {
    if (!user) return;
    const q = query(
      collection(db, "submissions"),
      where("studentUid", "==", user.uid)
    );
    return onSnapshot(q, (snap) => {
      const rows = snap.docs.map(
        (d) => ({ id: d.id, ...(d.data() as Omit<Submission, "id">) })
      );
      // Sort client-side to avoid needing a composite index.
      rows.sort(
        (a, b) => (b.createdAt?.toMillis() ?? 0) - (a.createdAt?.toMillis() ?? 0)
      );
      setSubmissions(rows);
    });
  }, [user]);

  const previewUrl = useMemo(
    () => (recorder.blob ? URL.createObjectURL(recorder.blob) : null),
    [recorder.blob]
  );
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const onSubmit = async () => {
    if (!recorder.blob) return;
    setError(null);
    setUploading(true);
    try {
      await uploadRecording(recorder.blob);
      recorder.reset(); // the new submission shows up via the listener
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* --- Record & upload --- */}
      <section className="rounded-xl bg-white p-6 shadow">
        <h2 className="text-lg font-semibold">Record your answer</h2>
        <p className="text-sm text-slate-500">Up to {MAX_SECONDS} seconds.</p>

        <div className="mt-4 flex items-center gap-3">
          {!recorder.isRecording ? (
            <button
              onClick={recorder.start}
              disabled={uploading}
              className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {recorder.blob ? "Re-record" : "Start recording"}
            </button>
          ) : (
            <button
              onClick={recorder.stop}
              className="rounded-lg bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700"
            >
              Stop
            </button>
          )}
          {recorder.isRecording && (
            <span className="font-mono text-sm text-slate-600">
              {recorder.seconds}s / {MAX_SECONDS}s
            </span>
          )}
        </div>

        {recorder.error && (
          <p className="mt-3 text-sm text-red-600">{recorder.error}</p>
        )}

        {previewUrl && !recorder.isRecording && (
          <div className="mt-4 space-y-3">
            <audio src={previewUrl} controls className="w-full" />
            <div className="flex gap-2">
              <button
                onClick={onSubmit}
                disabled={uploading}
                className="rounded-lg bg-green-600 px-4 py-2 font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {uploading ? "Uploading…" : "Submit for feedback"}
              </button>
              <button
                onClick={recorder.reset}
                className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50"
              >
                Discard
              </button>
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      {/* --- Your submissions --- */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Your submissions</h2>
        {submissions.length === 0 ? (
          <p className="text-sm text-slate-500">
            No submissions yet — record one above.
          </p>
        ) : (
          submissions.map((s) => (
            <article key={s.id} className="rounded-xl bg-white p-6 shadow">
              <header className="flex items-center justify-between">
                <p className="text-xs text-slate-400">
                  {s.createdAt?.toDate().toLocaleString() ?? "just now"}
                </p>
                <StatusBadge status={s.status} />
              </header>

              {s.audioUrl && (
                <audio src={s.audioUrl} controls className="mt-3 w-full" />
              )}

              {s.status === "processing" && (
                <p className="mt-3 text-sm text-slate-500">
                  Transcribing and generating feedback…
                </p>
              )}
              {s.status === "error" && (
                <p className="mt-3 text-sm text-red-600">
                  {s.error ?? "Processing failed."}
                </p>
              )}
              {s.status === "done" && (
                <div className="mt-4 space-y-4">
                  <FeedbackPanel submission={s} />
                  <TeacherFeedback submission={s} />
                </div>
              )}
            </article>
          ))
        )}
      </section>
    </div>
  );
}
