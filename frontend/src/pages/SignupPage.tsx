import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { UserPlus, Mail, User, Lock, Box, Loader2, Check } from "lucide-react";
import toast from "react-hot-toast";
import { register } from "../utils/api";
import { useAuthStore } from "../stores/useAuthStore";

export default function SignupPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  const pwdRules = {
    length: password.length >= 8,
    match: password.length > 0 && password === confirm,
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !username || !password) { toast.error("모든 항목을 입력하세요"); return; }
    if (!pwdRules.length) { toast.error("비밀번호는 최소 8자"); return; }
    if (!pwdRules.match) { toast.error("비밀번호가 일치하지 않습니다"); return; }
    setLoading(true);
    try {
      const r = await register({ email: email.trim(), username: username.trim(), password });
      setSession(r.user, r.access_token);
      toast.success("가입 완료! 환영합니다");
      navigate("/projects", { replace: true });
    } catch (e: any) {
      toast.error(e.message || "회원가입 실패");
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
          <h1 className="text-2xl font-semibold mb-1">회원가입</h1>
          <p className="text-sm text-zinc-500 mb-7">3D 생성을 시작하려면 계정을 만드세요</p>

          <form onSubmit={submit} className="space-y-4">
            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1.5 block">이메일</span>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
                <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-3 py-2.5 text-sm focus:border-violet-600 focus:ring-1 focus:ring-violet-600 outline-none transition-all"
                  placeholder="you@example.com" />
              </div>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1.5 block">사용자명</span>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
                <input type="text" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-3 py-2.5 text-sm focus:border-violet-600 focus:ring-1 focus:ring-violet-600 outline-none transition-all"
                  placeholder="3~30자, 영문/숫자/_/-" />
              </div>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1.5 block">비밀번호</span>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
                <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-3 py-2.5 text-sm focus:border-violet-600 focus:ring-1 focus:ring-violet-600 outline-none transition-all"
                  placeholder="8자 이상" />
              </div>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1.5 block">비밀번호 확인</span>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
                <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-3 py-2.5 text-sm focus:border-violet-600 focus:ring-1 focus:ring-violet-600 outline-none transition-all"
                  placeholder="다시 입력" />
              </div>
            </label>

            <div className="text-xs text-zinc-500 space-y-1">
              <div className={`flex items-center gap-1.5 ${pwdRules.length ? "text-emerald-400" : ""}`}>
                <Check className="w-3 h-3" />최소 8자
              </div>
              <div className={`flex items-center gap-1.5 ${pwdRules.match ? "text-emerald-400" : ""}`}>
                <Check className="w-3 h-3" />비밀번호 일치
              </div>
            </div>

            <button type="submit" disabled={loading}
              className="w-full mt-2 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2 transition-all shadow-lg shadow-violet-900/30">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
              {loading ? "가입 중..." : "가입하기"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-zinc-500">
            이미 계정이 있으세요?{" "}
            <Link to="/login" className="text-violet-400 hover:text-violet-300 font-medium">로그인</Link>
          </div>
        </div>

        <div className="text-center mt-6 text-xs text-zinc-700">
          <Link to="/" className="hover:text-zinc-500 transition-colors">← 홈으로</Link>
        </div>
      </motion.div>
    </div>
  );
}
