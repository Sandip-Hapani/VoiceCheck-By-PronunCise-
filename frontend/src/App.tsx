import { useAuth } from "./auth/AuthContext";
import Login from "./components/Login";
import RolePicker from "./components/RolePicker";
import StudentView from "./components/StudentView";
import TeacherView from "./components/TeacherView";

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center text-slate-500">
      {children}
    </div>
  );
}

export default function App() {
  const { user, profile, loading, profileLoading, logout } = useAuth();

  if (loading) return <FullScreen>Loading…</FullScreen>;
  if (!user) return <Login />;
  if (profileLoading) return <FullScreen>Loading your profile…</FullScreen>;
  if (!profile) return <RolePicker />;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <img
              src="/pronuncise-logo.png"
              alt="PronunCise"
              className="h-8 w-8 rounded-md object-contain"
              // Hide gracefully if the logo file hasn't been added yet.
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
            <h1 className="text-xl font-bold">VoiceCheck</h1>
            <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium capitalize text-indigo-700">
              {profile.role}
            </span>
          </div>
          <div className="flex items-center gap-4">
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
        {profile.role === "student" ? <StudentView /> : <TeacherView />}
      </main>
    </div>
  );
}
