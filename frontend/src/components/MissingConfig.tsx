import { missingFirebaseKeys } from "../firebase";

const ENV_NAMES: Record<string, string> = {
  apiKey: "VITE_FIREBASE_API_KEY",
  authDomain: "VITE_FIREBASE_AUTH_DOMAIN",
  projectId: "VITE_FIREBASE_PROJECT_ID",
  storageBucket: "VITE_FIREBASE_STORAGE_BUCKET",
  messagingSenderId: "VITE_FIREBASE_MESSAGING_SENDER_ID",
  appId: "VITE_FIREBASE_APP_ID",
};

/** Shown when the frontend was built without Firebase config. */
export default function MissingConfig() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-lg rounded-xl border border-amber-200 bg-amber-50 p-6">
        <h1 className="text-lg font-semibold text-amber-900">
          Firebase config missing
        </h1>
        <p className="mt-2 text-sm text-amber-800">
          The frontend was built without its Firebase web config, so it can't
          start. These <code>VITE_FIREBASE_*</code> values are inlined at{" "}
          <strong>build time</strong>:
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-900">
          {missingFirebaseKeys.map((k) => (
            <li key={k}>
              <code>{ENV_NAMES[k] ?? k}</code>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm text-amber-800">
          Set them in <code>.env</code> (Docker) or <code>frontend/.env.local</code>{" "}
          (npm), then rebuild: <code>docker compose up --build</code>.
        </p>
      </div>
    </div>
  );
}
