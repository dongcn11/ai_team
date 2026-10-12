import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.tsx";
import { AuthGate } from "./auth";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
  </React.StrictMode>,
);
