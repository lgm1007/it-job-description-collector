"use client";

import dynamic from "next/dynamic";

// Sign-in state and search conditions live in the browser, so the page renders only there.
const AuthGate = dynamic(() => import("@/components/AuthGate"), {
  ssr: false,
  loading: () => <p className="splash">connecting…</p>,
});

export default function Page() {
  return <AuthGate />;
}
