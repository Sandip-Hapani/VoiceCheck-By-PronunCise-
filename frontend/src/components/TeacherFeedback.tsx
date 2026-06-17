import type { Submission } from "../types";

/** Read-only teacher review shown to the student (or "pending"). */
export default function TeacherFeedback({ submission }: { submission: Submission }) {
  const reviewed = submission.reviewStatus === "reviewed";

  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Teacher feedback
        </h4>
        {reviewed ? (
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
            Reviewed
          </span>
        ) : (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            Pending review
          </span>
        )}
      </div>

      {reviewed ? (
        <div className="mt-2 space-y-2 text-sm">
          <p className="text-slate-700">
            Transcript{" "}
            {submission.transcriptVerified ? (
              <span className="font-medium text-green-700">verified as accurate ✓</span>
            ) : (
              <span className="font-medium text-amber-700">
                flagged as needing correction
              </span>
            )}
            .
          </p>
          {submission.teacherNotes ? (
            <p className="whitespace-pre-wrap text-slate-800">
              {submission.teacherNotes}
            </p>
          ) : (
            <p className="text-slate-400">No additional notes.</p>
          )}
          {submission.reviewedBy && (
            <p className="text-xs text-slate-400">— {submission.reviewedBy}</p>
          )}
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-500">
          Your teacher hasn’t reviewed this recording yet. Check back soon.
        </p>
      )}
    </div>
  );
}
