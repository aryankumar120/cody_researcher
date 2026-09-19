const BASE = "/api/research";

async function asJson(resp) {
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail || `request failed with ${resp.status}`);
  }
  return resp.json();
}

export function startResearch(target, task) {
  return fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, task }),
  }).then(asJson);
}

export function getRun(runId) {
  return fetch(`${BASE}/${runId}`).then(asJson);
}

export function getEvents(runId) {
  return fetch(`${BASE}/${runId}/events`).then(asJson);
}

export function resumeRun(runId) {
  return fetch(`${BASE}/${runId}/resume`, { method: "POST" }).then(asJson);
}
