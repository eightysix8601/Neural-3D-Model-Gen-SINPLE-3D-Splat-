import { useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { LogIn, Mail, Lock, Box, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import { login } from "../utils/api";
import { useAuthStore } from "../stores/useAuthStore";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((s) => s.setSession);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const redirectTo = (location.state as any)?.from ?? "/projects";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier || !password) {
      toast.error("이메일/아이디와 비밀번호를 입력하세요");
      return;
    }
    setLoading(true);
    try {
      const r = await login({ identifier: identifier.trim(), password });
      setSession(r.user, r.access_token);
      toast.success(`${r.user.username}님 환영합니다`);
      navigate(redirectTo, { replace: true });
    } catch (e: any) {
      toast.error(e.message || "로그인 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-gradient-radial from-violet-600/20 via-blue-600/5 to-transparent blur-3xl" />
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="relative w-full max-w-md">
        <Link to="/" className="flex items-center gap-2.5 justify-center mb-8 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-lg shadow-violet-900/40">
            <Box className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-lg bg-gradient-to-r from-violet-300 to-blue-300 bg-clip-text text-transparent">
            SnapAsset3D
          </span>
        </Link>

        <div className="bg-zinc-900/60 backdrop-blur border border-zinc-800 rounded-3xl p-8 shadow-2xl">
          <h1 className="text-2xl font-semibold mb-1">로그인</h1>
          <p className="text-sm text-zinc-500 mb-7">계정에 로그인해서 3D 모델을 생성하세요</p>

          <form onSubmit={submit} className="space-y-4">
            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1.5 block">이메일 또는 아이디</span>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
                <input type="text" autoComplete="username" value={identifier} onChange={(e) => setIdentifier(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-3 py-2.5 text-sm focus:border-violet-600 focus:ring-1 focus:ring-violet-600 outline-none transition-all"
                  placeholder="you@example.com" />
              </div>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1.5 block">비밀번호</span>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
                <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-3 py-2.5 text-sm focus:border-violet-600 focus:ring-1 focus:ring-violet-600 outline-none transition-all"
                  placeholder="••••••••" />
              </div>
            </label>

            <button type="submit" disabled={loading}
              className="w-full mt-2 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2 transition-all shadow-lg shadow-violet-900/30">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
              {loading ? "로그인 중..." : "로그인"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-zinc-500">
            처음이신가요?{" "}
            <Link to="/signup" className="text-violet-400 hover:text-violet-300 font-medium">회원가입</Link>
          </div>
        </div>

        <div className="text-center mt-6 text-xs text-zinc-700">
          <Link to="/" className="hover:text-zinc-500 transition-colors">← 홈으로</Link>
        </div>
      </motion.div>
    </div>
  );
}
