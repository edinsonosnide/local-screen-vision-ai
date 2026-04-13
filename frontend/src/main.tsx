import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// StrictMode is intentionally omitted — it double-invokes effects in dev,
// which creates a WebSocket reconnect storm via the async onclose race condition.
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
