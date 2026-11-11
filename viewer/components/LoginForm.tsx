"use client";

import { type AuthError, isAuthRetryableFetchError } from "@supabase/supabase-js";
import { type FormEvent, useState } from "react";

import { PAUSED_HINT, supabase } from "@/lib/supabase";

function describe(error: AuthError): string {
  if (error.code === "invalid_credentials") return "이메일 또는 비밀번호가 맞지 않습니다.";
  if (isAuthRetryableFetchError(error)) return `서버에 연결하지 못했습니다. ${PAUSED_HINT}`;
  return error.message;
}

export default function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setMessage(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setMessage(describe(error));
  }

  return (
    <main className="login">
      <form onSubmit={submit}>
        <h1 className="logo">
          dev-jobs<span className="dim">.kr</span>
        </h1>
        <label className="prompt">
          <span className="ps">@</span>
          <input
            type="email"
            placeholder="이메일"
            autoComplete="username"
            autoFocus
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="prompt">
          <span className="ps">*</span>
          <input
            type="password"
            placeholder="비밀번호"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "로그인 중…" : "로그인"}
        </button>
        {message && (
          <p className="err" role="alert">
            {message}
          </p>
        )}
        <p className="hint">개인용 서비스입니다. 가입은 받지 않습니다.</p>
      </form>
    </main>
  );
}
