/** Shared status pill used in both student and teacher views. */
export type DisplayStatus = "uploading" | "processing" | "done" | "error";

const STYLES: Record<DisplayStatus, string> = {
  uploading: "bg-amber-100 text-amber-800",
  processing: "bg-blue-100 text-blue-800",
  done: "bg-green-100 text-green-800",
  error: "bg-red-100 text-red-800",
};

const LABELS: Record<DisplayStatus, string> = {
  uploading: "Uploading",
  processing: "Processing",
  done: "Done",
  error: "Error",
};

export default function StatusBadge({ status }: { status: DisplayStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {(status === "uploading" || status === "processing") && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {LABELS[status]}
    </span>
  );
}
