import type { Timestamp } from "firebase/firestore";

/** A user's role, chosen once and stored in `users/{uid}`. */
export type Role = "student" | "teacher";

export interface UserProfile {
  uid: string;
  email: string;
  role: Role;
}

/** Pipeline status written by the backend. */
export type SubmissionStatus = "processing" | "done" | "error";

/** Whether a teacher has reviewed the submission yet. */
export type ReviewStatus = "pending" | "reviewed";

/** A submission document in the `submissions` Firestore collection. */
export interface Submission {
  id: string;
  studentEmail: string;
  studentUid: string;

  // Pipeline output (AI).
  status: SubmissionStatus;
  audioUrl: string;
  transcription: string;
  strengths: string[];
  improvements: string[];
  error?: string;

  // Teacher review.
  reviewStatus: ReviewStatus;
  transcriptVerified: boolean;
  teacherNotes: string;
  reviewedBy?: string;
  reviewedAt?: Timestamp;

  createdAt?: Timestamp;
  completedAt?: Timestamp;
}
