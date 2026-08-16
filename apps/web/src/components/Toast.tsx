"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { IconAlert, IconCheck, IconClose } from "./icons";

/**
 * Transient confirmations, in one place.
 *
 * Before this, every action reported itself differently — an inline red line
 * here, a silent success there — and a silent success is the worst of them: the
 * operator cannot tell a completed action from an ignored click, so they do it
 * twice. A toast says the thing happened, names what happened, and leaves.
 *
 * Errors do not auto-dismiss. A message you might have missed is not a message.
 */

type Tone = "ok" | "error";
type Message = { id: number; text: string; tone: Tone };

const ToastContext = createContext<{ show: (text: string, tone?: Tone) => void }>({
  show: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);

  const show = useCallback((text: string, tone: Tone = "ok") => {
    const id = Date.now() + Math.random();
    setMessages((current) => [...current, { id, text, tone }]);
    if (tone === "ok") {
      setTimeout(() => {
        setMessages((current) => current.filter((m) => m.id !== id));
      }, 4000);
    }
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 end-4 z-50 flex flex-col items-end gap-2"
        role="status"
        aria-live="polite"
      >
        {messages.map((message) => (
          <Toast
            key={message.id}
            message={message}
            onDismiss={() => setMessages((c) => c.filter((m) => m.id !== message.id))}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function Toast({ message, onDismiss }: { message: Message; onDismiss: () => void }) {
  const [entered, setEntered] = useState(false);

  // One frame at the start position, then the transition runs — a transition
  // from an already-visible default, so nothing flashes at full opacity first.
  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const isError = message.tone === "error";

  return (
    <div
      className="pointer-events-auto flex max-w-sm items-start gap-2.5 rounded-[var(--radius)] border px-3 py-2.5 text-[12.5px] shadow-[var(--shadow)] transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
      style={{
        borderColor: isError ? "var(--danger)" : "var(--line-strong)",
        background: "var(--panel-2)",
        color: "var(--fg)",
        opacity: entered ? 1 : 0,
        transform: entered ? "translateY(0)" : "translateY(6px)",
      }}
    >
      {isError ? (
        <IconAlert size={14} className="mt-px shrink-0 text-[var(--danger)]" />
      ) : (
        <IconCheck size={14} className="mt-px shrink-0 text-[var(--ok)]" />
      )}
      <span className="flex-1 leading-relaxed">{message.text}</span>
      <button
        onClick={onDismiss}
        aria-label="dismiss"
        className="shrink-0 text-[var(--fg-faint)] transition-colors hover:text-[var(--fg)]"
      >
        <IconClose size={12} />
      </button>
    </div>
  );
}
