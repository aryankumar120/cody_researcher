import { useState } from "react";

export default function ResearchForm({ onSubmit, busy }) {
  const [target, setTarget] = useState("");
  const [task, setTask] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const t = target.trim();
    const q = task.trim();
    if (!t || !q) return;
    onSubmit(t, q);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-1.5 mb-12">
      <label htmlFor="target" className="text-[13px] text-soft mt-3.5">
        Company, domain, or URL
      </label>
      <input
        id="target"
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        type="text"
        placeholder="Siemens"
        required
        className="text-[15px] px-3 py-2.5 border border-line rounded bg-panel text-ink
                   focus:outline-none focus:border-accent"
      />

      <label htmlFor="task" className="text-[13px] text-soft mt-3.5">
        What do you want to know
      </label>
      <textarea
        id="task"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        rows={2}
        placeholder="Find the company's major product areas and the markets mentioned on its official website."
        required
        className="text-[15px] px-3 py-2.5 border border-line rounded bg-panel text-ink resize-y
                   focus:outline-none focus:border-accent"
      />

      <button
        type="submit"
        disabled={busy}
        className="mt-5 self-start bg-accent text-white text-[15px] px-6 py-2.5 rounded
                   disabled:opacity-55 disabled:cursor-default"
      >
        {busy ? "Working..." : "Start research"}
      </button>
    </form>
  );
}
