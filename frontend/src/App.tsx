import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useEffect } from "react";
import GalleryPage      from "./pages/GalleryPage";
import MyProjectsPage   from "./pages/MyProjectsPage";
import LoginPage        from "./pages/LoginPage";
import SignupPage       from "./pages/SignupPage";
import CreatePage       from "./pages/CreatePage";
import ViewPage         from "./pages/ViewPage";
import RiggingPage      from "./pages/RiggingPage";
import ModelDetailPage  from "./pages/ModelDetailPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import AuthGuard        from "./components/AuthGuard";
import { useAuthStore } from "./stores/useAuthStore";

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => { hydrate(); }, [hydrate]);

  return (
    <BrowserRouter>
      <Toaster position="bottom-right" toastOptions={{
        style: { background: "#18181b", color: "#f4f4f5", border: "1px solid #3f3f46", borderRadius: "12px", fontSize: "13px" },
      }} />
      <Routes>
        {/* 공개 페이지 */}
        <Route path="/"          element={<GalleryPage />} />
        <Route path="/m/:id"     element={<ModelDetailPage />} />
        <Route path="/login"     element={<LoginPage />} />
        <Route path="/signup"    element={<SignupPage />} />

        {/* 로그인 필수 */}
        <Route path="/projects"    element={<AuthGuard><MyProjectsPage /></AuthGuard>} />
        <Route path="/create"      element={<AuthGuard><CreatePage /></AuthGuard>} />
        <Route path="/p/:id"       element={<AuthGuard><ProjectDetailPage /></AuthGuard>} />
        <Route path="/view/:id"    element={<AuthGuard><ViewPage /></AuthGuard>} />
        <Route path="/rigging/:id" element={<AuthGuard><RiggingPage /></AuthGuard>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
