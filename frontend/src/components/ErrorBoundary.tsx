import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/** Catches render-time errors so the app shows a message instead of a blank page. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Uncaught error:", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="max-w-lg rounded-xl border border-red-200 bg-red-50 p-6">
          <h1 className="text-lg font-semibold text-red-800">
            Something went wrong
          </h1>
          <p className="mt-2 text-sm text-red-700">
            The app failed to start. Check the browser console for details.
          </p>
          <pre className="mt-3 overflow-auto rounded bg-white p-3 text-xs text-red-900">
            {this.state.error.message}
          </pre>
        </div>
      </div>
    );
  }
}
