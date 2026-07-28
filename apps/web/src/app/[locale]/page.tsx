import { useTranslations } from "next-intl";

export default function HomePage() {
  const t = useTranslations();
  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-bold">{t("app.name")}</h1>
      <p className="text-sm opacity-70">{t("app.tagline")}</p>
    </main>
  );
}
