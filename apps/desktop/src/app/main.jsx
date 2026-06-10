import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { appendFrontendLog, readFrontendLogs } from "../shared/frontendLog.js";
import "../styles.css";

window.addEventListener("error", (event) => {
  appendFrontendLog({
    level: "error",
    source: "window.error",
    message: event.message,
    stack: event.error?.stack || "",
  });
});

window.addEventListener("unhandledrejection", (event) => {
  appendFrontendLog({
    level: "error",
    source: "unhandledrejection",
    message: event.reason?.message || String(event.reason || "Unhandled promise rejection"),
    stack: event.reason?.stack || "",
  });
});

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    appendFrontendLog({
      level: "error",
      source: "react.error_boundary",
      message: error?.message || String(error),
      stack: error?.stack || "",
      componentStack: info?.componentStack || "",
    });
  }

  render() {
    if (!this.state.error) return this.props.children;
    const logs = readFrontendLogs().slice(-12).reverse();
    return (
      <main className="fatal-screen">
        <section>
          <h1>前端渲染失败</h1>
          <p>{this.state.error.message || "Unknown frontend error"}</p>
          <pre>{this.state.error.stack || this.state.info?.componentStack || ""}</pre>
          <h2>最近前端日志</h2>
          <pre>{JSON.stringify(logs, null, 2)}</pre>
        </section>
      </main>
    );
  }
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
