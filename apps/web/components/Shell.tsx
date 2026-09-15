"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useDemo } from "./DemoProvider";
import { DEMO_STAGES } from "@/lib/demoStages";

const NAV_ITEMS = [
  { key: "dashboard", href: "/dashboard", icon: "▤" },
  { key: "liveMonitoring", href: "/live-monitoring", icon: "◎" },
  { key: "methaneEvents", href: "/events", icon: "⚠" },
  { key: "priorityCenter", href: "/priority-center", icon: "★" },
  { key: "analytics", href: "/analytics", icon: "▲" },
  { key: "workOrders", href: "/work-orders", icon: "▣" },
  { key: "facilities", href: "/facilities", icon: "⛯" },
  { key: "dataSources", href: "/data-sources", icon: "⇄" },
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const t = useTranslations();
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const demo = useDemo();

  const strippedPath = pathname.replace(`/${locale}`, "") || "/dashboard";

  function switchLocale(next: string) {
    const rest = pathname.replace(`/${locale}`, "");
    router.push(`/${next}${rest || "/dashboard"}`);
  }

  const stageIdx = demo.currentStageKey ? DEMO_STAGES.findIndex((s) => s.key === demo.currentStageKey) : -1;

  return (
    <div className="min-h-screen flex flex-col">
      <header
        className="flex items-center justify-between px-7"
        style={{ background: "var(--green)", height: 72 }}
      >
        <Link href={`/${locale}/dashboard`} className="flex items-center gap-2.5">
          <div
            className="flex items-center justify-center"
            style={{ width: 42, height: 42, borderRadius: 11, background: "var(--cream)", padding: 5 }}
          >
            <img src="/logo-mark.png" alt="" style={{ height: "100%", width: "auto", display: "block" }} />
          </div>
          <div className="flex flex-col" style={{ lineHeight: 1.05 }}>
            <span style={{ color: "#fff", fontWeight: 700, fontSize: 19, letterSpacing: 2.5 }}>
              {t("brand.name")}
            </span>
            <span style={{ color: "var(--text-onGreen-muted)", fontSize: 9.5, letterSpacing: 1.6, textTransform: "uppercase" }}>
              {t("brand.tagline")}
            </span>
          </div>
        </Link>

        <div className="flex items-center gap-4">
          <span className="demo-pill">
            <span className="dot" />
            {t("demo.badge")}
          </span>
          <button
            className="btn-primary"
            style={{ background: demo.running ? "var(--grey)" : "var(--peach)", color: "var(--umber)" }}
            disabled={demo.running}
            onClick={() => demo.runDemo()}
          >
            {demo.running ? t("demo.running") : t("demo.run")}
          </button>
          <button
            className="rounded-full text-xs font-semibold px-3 py-1.5"
            style={{ color: "var(--text-onGreen-muted)", border: "1px solid rgba(255,255,255,0.2)" }}
            onClick={() => demo.resetDemo()}
          >
            {t("demo.reset")}
          </button>
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-onGreen-muted)" }}>
            <button
              onClick={() => switchLocale("en")}
              style={{ fontWeight: locale === "en" ? 700 : 500, color: locale === "en" ? "#fff" : undefined }}
            >
              EN
            </button>
            <span>/</span>
            <button
              onClick={() => switchLocale("ar")}
              style={{ fontWeight: locale === "ar" ? 700 : 500, color: locale === "ar" ? "#fff" : undefined }}
            >
              عربي
            </button>
          </div>
        </div>
      </header>

      {demo.currentStageLabel && (
        <div
          className="flex items-center gap-3 px-7 py-2 text-xs overflow-x-auto"
          style={{ background: "var(--green-light)", color: "var(--text-onGreen-muted)" }}
        >
          <span style={{ color: "#fff", fontWeight: 700, flexShrink: 0 }}>{t("demo.stageLabel")}:</span>
          {DEMO_STAGES.map((s, i) => (
            <span
              key={s.key}
              className="flex items-center gap-1.5 flex-shrink-0"
              style={{ color: i <= stageIdx ? "var(--peach)" : "var(--text-onGreen-muted)", fontWeight: i === stageIdx ? 700 : 500 }}
            >
              <span
                className="inline-block rounded-full"
                style={{ width: 6, height: 6, background: i <= stageIdx ? "var(--peach)" : "rgba(255,255,255,0.25)" }}
              />
              {s.label}
              {i < DEMO_STAGES.length - 1 && <span style={{ opacity: 0.3 }}>→</span>}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-1" style={{ minHeight: "calc(100vh - 72px)" }}>
        <aside
          className="sidebar flex-shrink-0 flex flex-col"
          style={{ width: 250, background: "var(--green)", padding: "22px 14px" }}
        >
          <nav className="flex flex-col gap-0.5">
            {NAV_ITEMS.map((item) => {
              const active = strippedPath.startsWith(item.href);
              return (
                <Link
                  key={item.key}
                  href={`/${locale}${item.href}`}
                  className={`sidebar-nav-item ${active ? "active" : ""}`}
                >
                  <span style={{ width: 18, textAlign: "center" }}>{item.icon}</span>
                  {t(`nav.${item.key}`)}
                </Link>
              );
            })}
          </nav>

          <div className="mt-auto rounded-2xl overflow-hidden" style={{ background: "var(--green-light)" }}>
            <div
              className="flex items-center justify-center"
              style={{ height: 96, background: "var(--cream)" }}
            >
              <img src="/logo-mark.png" alt="" style={{ height: 72, width: "auto" }} />
            </div>
            <div className="p-4">
              <div style={{ color: "#fff", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>
                {t("brand.name")}
              </div>
              <div style={{ color: "var(--text-onGreen-muted)", fontSize: 11.5, lineHeight: 1.5, marginBottom: 12 }}>
                {t("footer.tagline")}
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="rounded-sm overflow-hidden flex"
                  style={{ width: 22, height: 15, boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.15)" }}
                >
                  <div style={{ width: 8, background: "#DA291C" }} />
                  <div className="flex-1 flex flex-col">
                    <span style={{ flex: 1, background: "#fff" }} />
                    <span style={{ flex: 1, background: "#DA291C" }} />
                    <span style={{ flex: 1, background: "#1D4533" }} />
                  </div>
                </div>
                <span style={{ color: "var(--text-onGreen-muted)", fontSize: 10, letterSpacing: 1 }}>
                  {t("footer.vision")}
                </span>
              </div>
            </div>
          </div>
        </aside>

        <main className="flex-1 min-w-0" style={{ padding: "30px 34px 50px" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
