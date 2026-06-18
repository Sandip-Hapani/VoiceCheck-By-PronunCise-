import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import ErrorBoundary from "./components/ErrorBoundary";
import MissingConfig from "./components/MissingConfig";
import { firebaseConfigured } from "./firebase";
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root")!);

// Without Firebase config the app can't do anything — show a clear setup screen
// instead of a blank page.
root.render(
  <React.StrictMode>
    {firebaseConfigured ? (
      <ErrorBoundary>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ErrorBoundary>
    ) : (
      <MissingConfig />
    )}
  </React.StrictMode>
);
