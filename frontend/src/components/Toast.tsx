// Lightweight toast notifications (success / error / info).
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, X } from "lucide-react";

type Kind = "success" | "error" | "info";
interface Toast { id: number; kind: Kind; title: string; message?: string }

const Ctx = createContext<(kind: Kind, title: string, message?: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const remove = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));
  const push = useCallback((kind: Kind, title: string, message?: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, kind, title, message }]);
    window.setTimeout(() => remove(id), kind === "error" ? 8000 : 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-900">
            {t.kind === "success" ? <CircleCheck className="mt-0.5 h-5 w-5 text-emerald-500" /> : t.kind === "error" ? <CircleAlert className="mt-0.5 h-5 w-5 text-rose-500" /> : <Info className="mt-0.5 h-5 w-5 text-sky-500" />}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900 dark:text-white">{t.title}</p>
              {t.message && <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{t.message}</p>}
            </div>
            <button aria-label="Dismiss" onClick={() => remove(t.id)} className="text-slate-400 hover:text-slate-600"><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
