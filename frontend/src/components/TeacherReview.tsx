import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { saveTeacherReview } from "../lib/reviews";
import type { Submission } from "../types";

/** Editable teacher review: verify the AI transcript + leave improvement notes. */
export default function TeacherReview({ submission }: { submission: Submission }) {
  const { user } = useAuth();
  const [verified, setVerified] = useState(submission.transcriptVerified);
  const [notes, setNotes] = useState(submission.teacherNotes ?? "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(submission.reviewStatus === "reviewed");

  const dirty =
    verified !== submission.transcriptVerified ||
    notes !== (submission.teacherNotes ?? "");

  const save = async () => {
    setBusy(true);
    try {
      await saveTeacherReview(submission.id, {
        transcriptVerified: verified,
        teacherNotes: notes.trim(),
        reviewedBy: user?.email ?? "unknown",
      });
      setSaved(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Your review
        </h4>
        {saved && !dirty && (
          <span className="text-xs font-medium text-green-700">Saved ✓</span>
        )}
      </div>

      <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={verified}
          onChange={(e) => setVerified(e.target.checked)}
          className="h-4 w-4 rounded border-slate-300"
        />
        AI transcript is accurate
      </label>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Improvement notes for the student…"
        rows={3}
        className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />

      <button
        onClick={save}
        disabled={busy || (saved && !dirty)}
        className="mt-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {busy ? "Saving…" : saved ? "Update review" : "Save review"}
      </button>
    </div>
  );
}
