import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import type { Role } from "../types";

/** Shown once after first login: pick whether this account is a student or teacher. */
export default function RolePicker() {
  const { setRole, logout, user } = useAuth();
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = async (role: Role) => {
    setError(null);
    setBusy(role);
    try {
      await setRole(role);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save role");
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow p-6 space-y-5 text-center">
        <div>
          <h1 className="text-2xl font-bold">Welcome to VoiceCheck</h1>
          <p className="text-sm text-slate-500">
            Signed in as {user?.email}. How will you use this account?
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <RoleCard
            title="Student"
            desc="Record and submit audio, then read your feedback."
            onClick={() => choose("student")}
            busy={busy === "student"}
          />
          <RoleCard
            title="Teacher"
            desc="Review all submissions and leave improvement notes."
            onClick={() => choose("teacher")}
            busy={busy === "teacher"}
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button onClick={logout} className="text-sm text-slate-500 hover:underline">
          Sign out
        </button>
      </div>
    </div>
  );
}

function RoleCard({
  title,
  desc,
  onClick,
  busy,
}: {
  title: string;
  desc: string;
  onClick: () => void;
  busy: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="rounded-xl border border-slate-200 p-4 text-left hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50"
    >
      <div className="font-semibold">{busy ? "Saving…" : title}</div>
      <div className="mt-1 text-xs text-slate-500">{desc}</div>
    </button>
  );
}
