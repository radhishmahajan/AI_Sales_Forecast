// Searchable product selector (type a code or name; shows up to 50 matches).
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { cx } from "./ui";

export interface PickerItem { StockCode: string; Description: string; abc_class?: string }

export function ProductPicker({ items, value, onChange, label = "Product" }: {
  items: PickerItem[]; value: string | null; onChange: (code: string) => void; label?: string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const selected = items.find((i) => i.StockCode === value);
  const matches = useMemo(() => {
    const q = query.trim().toUpperCase();
    const list = q ? items.filter((i) => i.StockCode.toUpperCase().includes(q) || (i.Description ?? "").toUpperCase().includes(q)) : items;
    return list.slice(0, 50);
  }, [items, query]);

  return (
    <div className="relative">
      <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">{label}</label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
        <input
          aria-label={label}
          role="combobox"
          aria-expanded={open}
          className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-950"
          placeholder="Search by product name or code…"
          value={open ? query : selected ? `${selected.StockCode} — ${selected.Description}` : query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={(e) => { setQuery(""); setOpen(true); e.currentTarget.select(); }}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        />
      </div>
      {open && (
        <ul role="listbox" className="scrollbar-thin absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {matches.length === 0 && <li className="px-3 py-2 text-slate-500">No matching products</li>}
          {matches.map((m) => (
            <li key={m.StockCode} role="option" aria-selected={m.StockCode === value}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { onChange(m.StockCode); setQuery(""); setOpen(false); }}
                className={cx("flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-indigo-50 dark:hover:bg-slate-800", m.StockCode === value && "bg-indigo-50 dark:bg-slate-800")}
              >
                <span className="w-16 shrink-0 font-mono text-xs text-slate-500">{m.StockCode}</span>
                <span className="truncate">{m.Description}</span>
                {m.abc_class && <span className="ml-auto text-[10px] text-slate-400">{m.abc_class}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
