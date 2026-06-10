export function displayStatusFromSession(session) {
  const latestRun = session && typeof session.latest_run === "object" ? session.latest_run : {};
  const runStatus = String(latestRun.status || latestRun.result_status || "").trim();
  if (runStatus) return runStatus;
  return String(session?.status || "idle").trim() || "idle";
}
