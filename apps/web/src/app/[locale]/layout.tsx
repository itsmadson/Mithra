import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import "maplibre-gl/dist/maplibre-gl.css";
import "../globals.css";

/*
 * Fonts come from the platform, not from a webfont service.
 *
 * next/font/google fetches at build time, and this network cannot reach
 * fonts.googleapis.com, jsdelivr, or unpkg — the build failed outright on
 * `Failed to fetch Inter from Google Fonts`. A survey tool that cannot be
 * rebuilt offline is not much use, so the stacks in globals.css name the
 * Persian faces a Windows or Linux machine in Iran actually has (Vazirmatn,
 * Sahel, Tahoma) and fall back through system-ui.
 *
 * To upgrade: drop a woff2 into public/fonts and switch to next/font/local,
 * which needs no network at all.
 */

export const metadata = {
  title: "بینا · Bina",
  description: "Count and classify urban signs from street-level imagery",
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const messages = await getMessages();
  const isFa = locale === "fa";

  return (
    <html
      lang={locale}
      dir={isFa ? "rtl" : "ltr"}
      data-theme="dark"
      suppressHydrationWarning
    >
      <head>
        {/* Applied before paint so a stored light preference never flashes dark. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('bina-theme');if(t){document.documentElement.dataset.theme=t}}catch(e){}`,
          }}
        />
      </head>
      <body>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
