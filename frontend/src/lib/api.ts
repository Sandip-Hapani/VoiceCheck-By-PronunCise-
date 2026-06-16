import { auth } from "../firebase";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/**
 * Upload a recorded audio blob to the backend. The backend creates the
 * Firestore submission document and kicks off async processing; the UI then
 * tracks status via the Firestore real-time listener (not this response).
 */
export async function uploadRecording(blob: Blob): Promise<{ id: string }> {
  const token = await auth.currentUser?.getIdToken();
  if (!token) throw new Error("Not authenticated");

  const form = new FormData();
  form.append("audio", blob, "recording.webm");

  const res = await fetch(`${API_BASE_URL}/api/submissions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }
  return res.json();
}
