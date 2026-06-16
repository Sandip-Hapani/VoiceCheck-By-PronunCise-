import { useCallback, useEffect, useRef, useState } from "react";

const MAX_SECONDS = 30;

export interface RecorderState {
  isRecording: boolean;
  seconds: number;
  blob: Blob | null;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/**
 * Records up to 30s of audio via MediaRecorder (webm/opus) and auto-stops at
 * the limit. Exposes a live seconds counter for the UI.
 */
export function useRecorder(): RecorderState {
  const [isRecording, setIsRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const stop = useCallback(() => {
    recorderRef.current?.stop();
    recorderRef.current?.stream.getTracks().forEach((t) => t.stop());
    clearTimer();
    setIsRecording(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setBlob(null);
    setSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        setBlob(new Blob(chunksRef.current, { type: "audio/webm" }));
      };

      recorder.start();
      recorderRef.current = recorder;
      setIsRecording(true);

      timerRef.current = window.setInterval(() => {
        setSeconds((s) => {
          const next = s + 1;
          // Defer stop() so we don't trigger another state update mid-updater.
          if (next >= MAX_SECONDS) window.setTimeout(stop, 0);
          return Math.min(next, MAX_SECONDS);
        });
      }, 1000);
    } catch {
      setError("Microphone access denied or unavailable.");
    }
  }, [stop]);

  const reset = useCallback(() => {
    setBlob(null);
    setSeconds(0);
    setError(null);
  }, []);

  // Clean up the interval if the component unmounts mid-recording.
  useEffect(() => clearTimer, []);

  return { isRecording, seconds, blob, error, start, stop, reset };
}
