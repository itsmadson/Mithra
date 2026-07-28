import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";

export const locales = ["fa", "en"] as const;
export const defaultLocale = "fa";

export default getRequestConfig(async ({ requestLocale }) => {
  const locale = (await requestLocale) ?? defaultLocale;
  if (!locales.includes(locale as (typeof locales)[number])) notFound();
  return { locale, messages: (await import(`../messages/${locale}.json`)).default };
});
