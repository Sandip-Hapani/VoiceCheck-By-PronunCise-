import type { Submission } from "../types";

/** Renders the transcription + AI feedback for a completed submission. */
export default function FeedbackPanel({ submission }: { submission: Submission }) {
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Transcription
        </h4>
        <p className="mt-1 text-slate-800">
          {submission.transcription || <em className="text-slate-400">empty</em>}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <FeedbackList
          title="Strengths"
          items={submission.strengths}
          tone="text-green-700"
        />
        <FeedbackList
          title="Improvements"
          items={submission.improvements}
          tone="text-amber-700"
        />
      </div>
    </div>
  );
}

function FeedbackList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: string;
}) {
  return (
    <div>
      <h4 className={`text-xs font-semibold uppercase tracking-wide ${tone}`}>
        {title}
      </h4>
      {items.length ? (
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-800">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-slate-400">None</p>
      )}
    </div>
  );
}
