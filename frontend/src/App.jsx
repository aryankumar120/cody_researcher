import { useState, useRef, useCallback } from "react";
import ResearchForm from "./components/ResearchForm.jsx";
import StatusPanel from "./components/StatusPanel.jsx";
import AnswerPanel from "./components/AnswerPanel.jsx";
import SourcesPanel from "./components/SourcesPanel.jsx";
import LogPanel from "./components/LogPanel.jsx";
import { startResearch, getRun, getEvents, resumeRun } from "./api.js";

const RUNNING_STATES = new Set(["pending", "running", "resuming"]);

export default function App() {
  const [run, setRun] = useState(null);
  const [citations, setCitations] = useState([]);
  const [events, setEvents] = useState([]);
  const runIdRef = useRef(null);
  const pollRef = useRef(null);

  const poll = useCallback(async () => {
    const runId = runIdRef.current;
    if (!runId) return;
    try {
      const data = await getRun(runId);
      setRun(data.run);
      if (!RUNNING_STATES.has(data.run.status)) {
        setCitations(data.citations || []);
        clearInterval(pollRef.current);
      }
      const evData = await getEvents(runId);
      setEvents(evData.events || []);
    } catch (err) {
      console.error(err);
    }
  }, []);

  function startPolling(runId) {
    runIdRef.current = runId;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(poll, 2000);
    poll();
  }

  async function handleSubmit(target, task) {
    setRun({ status: "pending" });
    setCitations([]);
    setEvents([]);
    try {
      const data = await startResearch(target, task);
      startPolling(data.run_id);
    } catch (err) {
      setRun({ status: "failed", error: err.message });
    }
  }

  async function handleResume() {
    if (!runIdRef.current) return;
    setRun((r) => ({ ...r, status: "resuming" }));
    try {
      await resumeRun(runIdRef.current);
      startPolling(runIdRef.current);
    } catch (err) {
      setRun((r) => ({ ...r, status: "failed", error: err.message }));
    }
  }

  const busy = run ? RUNNING_STATES.has(run.status) : false;
  const hasStarted = run !== null;

  return (
    <div
      className={`min-h-screen w-full ${
        hasStarted ? "" : "flex items-center justify-center"
      }`}
    >
      <div className="w-full max-w-content mx-auto px-6 py-16 pb-24">
        <header className="mb-10">
          <h1 className="font-serif text-[34px] font-semibold mb-2 tracking-tight">
            Cody Researcher
          </h1>
          <p className="text-soft text-[15px] max-w-[52ch]">
            Give it a company and a question. It finds the official site, reads what it needs to, and
            answers with sources.
          </p>
        </header>

        <ResearchForm onSubmit={handleSubmit} busy={busy} />

        <StatusPanel run={run} onResume={handleResume} />
        <AnswerPanel run={run} />
        <SourcesPanel citations={citations} />
        <LogPanel events={events} />
      </div>
    </div>
  );
}
