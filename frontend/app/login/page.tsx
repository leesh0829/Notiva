"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { hasStoredToken, login, register } from "@/lib/api";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hasStoredToken()) {
      router.replace("/dashboard");
    }
  }, [router]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setLoading(true);
      setError(null);
      if (mode === "login") {
        await login({ email, password });
      } else {
        await register({ email, password });
      }
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "인증 요청에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-2xl font-semibold text-slate-900">Notiva 로그인</h1>
      <p className="mt-1 text-sm text-slate-600">운영용 계정으로 로그인하거나 새 계정을 생성하세요.</p>

      <div className="mt-4 flex gap-2">
        <Button
          type="button"
          variant={mode === "login" ? "default" : "outline"}
          onClick={() => setMode("login")}
        >
          로그인
        </Button>
        <Button
          type="button"
          variant={mode === "register" ? "default" : "outline"}
          onClick={() => setMode("register")}
        >
          회원가입
        </Button>
      </div>

      <form className="mt-5 space-y-4" onSubmit={onSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">이메일</label>
          <input
            type="email"
            required
            autoComplete="email"
            className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">비밀번호</label>
          <input
            type="password"
            required
            minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="8자 이상"
          />
        </div>
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "처리 중..." : mode === "login" ? "로그인" : "회원가입 후 시작"}
        </Button>
      </form>

      <p className="mt-4 text-xs text-slate-500">
        로그인 후 <Link href="/dashboard" className="underline">대시보드</Link>로 이동합니다.
      </p>
    </section>
  );
}

