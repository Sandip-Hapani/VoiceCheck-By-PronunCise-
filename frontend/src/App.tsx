import { useState } from "react";
import { useAuth } from "./auth/AuthContext";
import Login from "./components/Login";
import StudentView from "./components/StudentView";
import TeacherView from "./components/TeacherView";

type Role = "student" | "teacher";

export default function App() {
  const { user, loading, logout } = useAuth();
  const [role, setRole] = useState<Role>("student");

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Loading…
      </div>
    );
  }

  if (!user) return <Login />;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between p-4">
          <h1 className="text-xl font-bold">VoiceCheck</h1>

          {/* Role toggle: there is no role management requirement, so a simple
              switch lets one account demo both views. See README. */}
          <div className="flex items-center gap-4">
            <div className="flex rounded-lg bg-slate-100 p-1 text-sm">
              {(["student", "teacher"] as Role[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setRole(r)}
                  className={`rounded-md px-3 py-1 capitalize ${
                    role === r ? "bg-white shadow font-medium" : "text-slate-500"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
            <span className="hidden text-sm text-slate-500 sm:inline">
              {user.email}
            </span>
            <button
              onClick={logout}
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="p-4 py-8">
        {role === "student" ? <StudentView /> : <TeacherView />}
      </main>
    </div>
  );
}
