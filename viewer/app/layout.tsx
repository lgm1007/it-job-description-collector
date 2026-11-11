import type { Metadata, Viewport } from "next";

import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

// Linked rather than bundled: Hangul comes in hundreds of small files, of which the browser fetches
// only those it needs, and downloading them all at build time is slow and can fail the build.
const FONTS = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Nanum+Gothic+Coding:wght@400;700&display=swap";

export const metadata: Metadata = {
  title: "dev-jobs · 개발자 채용 모아보기",
  description: "국내 채용 사이트의 개발자 공고를 한 곳에서 찾아봅니다.",
  manifest: "/manifest.webmanifest",
  robots: { index: false, follow: false }, // for personal use: keep it out of search engines
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0c0f0e",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" data-theme="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href={FONTS} />
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
