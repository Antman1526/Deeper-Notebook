import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";
import "./globals.css";
import "katex/dist/katex.min.css";
// ONP shadow-layer design tokens — layered on top of shadcn variables. See
// components/deeper-notebook/README.md for the pattern.
import "@/components/deeper-notebook/tokens.css";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { ConnectionGuard } from "@/components/common/ConnectionGuard";
import { themeScript } from "@/lib/theme-script";
import { I18nProvider } from "@/components/providers/I18nProvider";
// v0.8.70 — skippable, once-per-user "Aurora Reveal" launch intro.
import { IntroReveal } from "@/components/intro/IntroReveal";

const inter = Inter({ subsets: ["latin"], variable: "--font-dn-sans" });
const newsreader = Newsreader({ subsets: ["latin"], variable: "--font-dn-editorial" });

export const metadata: Metadata = {
  title: "Deeper Notebook",
  description: "Local-first research and knowledge workspace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${inter.variable} ${newsreader.variable} font-sans`}>
        <ErrorBoundary>
          <ThemeProvider>
            <QueryProvider>
              <I18nProvider>
                <ConnectionGuard>
                  {children}
                  <IntroReveal />
                  <Toaster />
                </ConnectionGuard>
              </I18nProvider>
            </QueryProvider>
          </ThemeProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
