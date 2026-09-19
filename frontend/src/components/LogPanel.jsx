import { useState, useEffect, useRef } from "react";

function shorten(detailJson) {
  try {
    const obj = JSON.parse(detailJson);
    return Object.entries(obj)
      .map(([k, v]) => `${k}: ${String(v).slice(0, 80)}`)
      .join(", ");
  } catch {
    return detailJson;
  }
}

export default function LogPanel({ events }) {
  const [open, setOpen] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events, open]);

  if (!events || events.length === 0) return null;

  const visible = events.slice(-150);

  return (
    <section className="mb-10">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-[13px] text-soft border border-line rounded px-3 py-1.5
                   hover:border-accent hover:text-accent"
      >
        {open ? "Hide run log" : "Show run log"}
      </button>
      {open && (
        <div
          ref={listRef}
          className="mt-3 text-[12.5px] text-soft max-h-[340px] overflow-y-auto border border-line rounded"
        >
          <ul>
            {visible.map((ev) => (
              <li key={ev.id} className="px-2.5 py-1.5 border-b border-line last:border-b-0">
                <span className="text-ink font-semibold">{ev.kind}</span>
                {" - "}
                {new Date(ev.ts * 1000).toLocaleTimeString()}
                {" - "}
                {shorten(ev.detail)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
