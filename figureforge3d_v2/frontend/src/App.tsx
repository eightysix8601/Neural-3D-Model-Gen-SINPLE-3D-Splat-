import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import HomePage   from "./pages/HomePage";
import CreatePage from "./pages/CreatePage";
import ViewPage   from "./pages/ViewPage";

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="bottom-right" toastOptions={{
        style: { background:"#18181b", color:"#f4f4f5", border:"1px solid #3f3f46", borderRadius:"12px", fontSize:"13px" },
      }} />
      <Routes>
        <Route path="/"         element={<HomePage />} />
        <Route path="/create"   element={<CreatePage />} />
        <Route path="/view/:id" element={<ViewPage />} />
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
