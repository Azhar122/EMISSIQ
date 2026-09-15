import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import { locales } from "@/i18n/config";
import { DemoProvider } from "@/components/DemoProvider";
import { Shell } from "@/components/Shell";
import "../globals.css";

export const metadata: Metadata = {
  title: "EMISSIQ — AI Methane Intelligence Platform",
  description: "Simulated demonstration prototype for AI-driven methane management",
  icons: { icon: "/favicon.png", apple: "/apple-touch-icon.png" },
};

// No generateStaticParams: every page here reads live backend state (events,
// sensor ticks, work orders), so static prerendering would just bake in stale
// data. Dynamic rendering is the correct default for this app.
export const dynamic = "force-dynamic";

export default async function LocaleLayout({
  children,
  params: { locale },
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  if (!locales.includes(locale as any)) notFound();
  const messages = await getMessages();
  const dir = locale === "ar" ? "rtl" : "ltr";

  return (
    <html lang={locale} dir={dir} data-theme="light">
      <body>
        <NextIntlClientProvider messages={messages}>
          <DemoProvider>
            <Shell>{children}</Shell>
          </DemoProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
