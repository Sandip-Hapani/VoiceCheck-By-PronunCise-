import type { Timestamp } from "firebase/firestore";

/** Status values written by the backend pipeline. */
export type SubmissionStatus = "processing" | "done" | "error";

/** A submission document in the `submissions` Firestore collection. */
export interface Submission {
  id: string;
  studentEmail: string;
  studentUid: string;
  status: SubmissionStatus;
  audioUrl: string;
  transcription: string;
  strengths: string[];
  improvements: string[];
  error?: string;
  createdAt?: Timestamp;
  completedAt?: Timestamp;
}

/** A teacher comment in the `submissions/{id}/comments` subcollection. */
export interface Comment {
  id: string;
  text: string;
  authorEmail: string;
  createdAt?: Timestamp;
}
