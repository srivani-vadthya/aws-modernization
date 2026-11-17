import { Navigate, Route, Routes } from "react-router-dom";
import { EngagementPage } from "./pages/EngagementPage";
import { HomePage } from "./pages/HomePage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/e/:id" element={<EngagementPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
