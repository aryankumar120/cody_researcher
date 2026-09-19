const DOT_CLASS = {
  ok: "bg-accent",
  fail: "bg-fail",
  warn: "bg-warn",
};

const LABELS = {
  pending: "Starting up...",
  running: "Researching",
  resuming: "Resuming...",
  completed: "Done",
  completed_with_failures: "Done - some pages failed",
  partial: "Stopped early (limit reached)",
  failed: "Failed",
};

export default function StatusPanel({ run, onResume }) {
  if (!run) return null;

  const dotTone = run.status === "completed" ? "ok" : run.status === "failed" ? "fail" : "warn";
  const label =
    run.status === "running"
      ? `Researching - ${run.pages_fetched || 0} pages read so far`
      : LABELS[run.status] || run.status;

  const showResume = run.status === "partial";

  return (
    <section className="mb-10">
      <div className="flex items-center gap-2.5 mb-2">
        <span className={`w-[9px] h-[9px] rounded-full flex-shrink-0 ${DOT_CLASS[dotTone]}`} />
        <span className="text-sm text-soft">{label}</span>
        {showResume && (
          <button
            onClick={onResume}
            className="text-[13px] text-soft border border-line rounded px-3 py-1.5
                       hover:border-accent hover:text-accent"
          >
            Resume this run
          </button>
        )}
      </div>
      <div className="flex gap-[18px] text-[13px] text-soft">
        <span>{run.pages_fetched || 0} pages</span>
        <span>{run.llm_calls || 0} model calls</span>
        <span>{run.iterations || 0} iterations</span>
      </div>
    </section>
  );
}
