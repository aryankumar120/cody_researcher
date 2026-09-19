const DONE_STATES = new Set(["completed", "completed_with_failures", "partial", "failed"]);

export default function AnswerPanel({ run }) {
  if (!run || !DONE_STATES.has(run.status)) return null;

  if (run.status === "failed") {
    return (
      <section className="mb-10">
        <h2 className="text-base font-semibold mb-3 border-b border-line pb-2">Answer</h2>
        <p className="text-[16px] whitespace-pre-wrap">
          {run.error || "The run failed before producing an answer."}
        </p>
      </section>
    );
  }

  return (
    <section className="mb-10">
      <h2 className="text-base font-semibold mb-3 border-b border-line pb-2">Answer</h2>
      <p className="text-[16px] whitespace-pre-wrap">{run.final_answer}</p>
      {run.coverage_note && (
        <p className="text-[13px] text-soft italic mt-2.5">{run.coverage_note}</p>
      )}
    </section>
  );
}
