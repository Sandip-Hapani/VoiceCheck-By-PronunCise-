import { doc, serverTimestamp, updateDoc } from "firebase/firestore";
import { db } from "../firebase";

/** Persist a teacher's review (transcript verification + improvement notes). */
export async function saveTeacherReview(
  submissionId: string,
  review: { transcriptVerified: boolean; teacherNotes: string; reviewedBy: string }
): Promise<void> {
  await updateDoc(doc(db, "submissions", submissionId), {
    reviewStatus: "reviewed",
    transcriptVerified: review.transcriptVerified,
    teacherNotes: review.teacherNotes,
    reviewedBy: review.reviewedBy,
    reviewedAt: serverTimestamp(),
  });
}
