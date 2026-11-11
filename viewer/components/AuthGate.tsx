"use client";

import type { Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

import { supabase } from "@/lib/supabase";

import JobsApp from "./JobsApp";
import LoginForm from "./LoginForm";

export default function AuthGate() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    if (!supabase) return;
    let live = true;
    supabase.auth.getSession().then(({ data }) => {
      if (live) setSession(data.session);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => {
      live = false;
      data.subscription.unsubscribe();
    };
  }, []);

  if (!supabase) {
    return (
      <p className="splash">
        NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY 환경변수가 없습니다. README의 &apos;웹앱 배포&apos;를 참고해 주세요.
      </p>
    );
  }
  if (session === undefined) return <p className="splash">connecting…</p>;
  if (!session) return <LoginForm />;
  return <JobsApp email={session.user.email} />;
}
