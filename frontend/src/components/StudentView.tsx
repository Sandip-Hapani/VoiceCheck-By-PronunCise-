import { useEffect, useMemo, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "../firebase";
import { uploadRecording } from "../lib/api";
import type { Submission } from "../types";
import { useRecorder } from "./useRecorder";
import StatusBadge, { type DisplayStatus } from "./StatusBadge";
import FeedbackPanel from "./FeedbackPanel";

const MAX_SECONDS = 30;

export default function StudentView() {
  const recorder = useRecorder();
  const [uploading, setUploading] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Real-time listener: this is what drives Processing -> Done live.
  useEffect(() => {
    if (!activeId) return;
    const unsub = onSnapshot(doc(db, "submissions", activeId), (snap) => {
      if (snap.exists()) {
        setSubmission({ id: snap.id, ...(snap.data() as Omit<Submission, "id">) });
      }
    });
    return unsub;
  }, [activeId]);

  // "Uploading" is a client-side state until the listener takes over.
  const displayStatus: DisplayStatus | null = useMemo(() => {
    if (uploading) return "uploading";
    if (submission) return submission.status as DisplayStatus;
    return null;
  }, [uploading, submission]);

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
    setSubmission(null);
    setActiveId(null);
    setUploading(true);
    try {
      const { id } = await uploadRecording(recorder.blob);
      setActiveId(id); // listener attaches; backend will flip to done
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const startOver = () => {
    recorder.reset();
    setActiveId(null);
    setSubmission(null);
    setError(null);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
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
                Submit for feedback
              </button>
              <button
                onClick={startOver}
                className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50"
              >
                Discard
              </button>
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      {displayStatus && (
        <section className="rounded-xl bg-white p-6 shadow">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Your submission</h3>
            <StatusBadge status={displayStatus} />
          </div>

          {displayStatus === "uploading" && (
            <p className="mt-3 text-sm text-slate-500">Uploading your recording…</p>
          )}
          {displayStatus === "processing" && (
            <p className="mt-3 text-sm text-slate-500">
              Transcribing and generating feedback…
            </p>
          )}
          {displayStatus === "error" && (
            <p className="mt-3 text-sm text-red-600">
              {submission?.error ?? "Something went wrong."}
            </p>
          )}
          {displayStatus === "done" && submission && (
            <div className="mt-4">
              <FeedbackPanel submission={submission} />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
