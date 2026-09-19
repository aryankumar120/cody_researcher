export default function SourcesPanel({ citations }) {
  if (!citations || citations.length === 0) return null;

  const seen = new Set();
  const unique = citations.filter((c) => {
    const key = c.source_url + c.source_snippet;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <section className="mb-10">
      <h2 className="text-base font-semibold mb-3 border-b border-line pb-2">Sources</h2>
      <ol className="pl-5 space-y-3.5">
        {unique.map((c, i) => (
          <li key={i} className="text-sm">
            <div className={`break-all ${c.valid ? "text-accent" : "text-fail"}`}>
              {c.source_url}
              <span className="inline-block text-[11px] text-soft bg-accent-soft rounded px-1.5 py-px ml-1.5">
                {c.evidence_kind}
              </span>
              {!c.valid && (
                <span className="inline-block text-[11px] text-fail bg-accent-soft rounded px-1.5 py-px ml-1.5">
                  unverified citation
                </span>
              )}
            </div>
            <div className="text-soft mt-0.5">{c.source_snippet}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}
