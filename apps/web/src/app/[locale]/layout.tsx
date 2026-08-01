import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import localFont from "next/font/local";
import "maplibre-gl/dist/maplibre-gl.css";
import "../globals.css";
import { StaleBuildRecovery } from "../../components/StaleBuildRecovery";
import { currentBuildId } from "../../lib/buildId";

/*
 * One family, both scripts, shipped with the app.
 *
 * Vazirmatn is drawn for Persian rather than adapted to it, and carries a
 * Latin companion designed alongside — so the same face sets a street name and
 * a model version without the seam that appears when a Latin family falls back
 * to a system Arabic face mid-sentence. It is a variable font, so the whole
 * weight range costs one 111 KB file.
 *
 * Self-hosted deliberately: this network cannot reach Google Fonts, and a
 * survey tool that cannot be rebuilt offline is not much use. next/font/local
 * subsets nothing away and needs no network at build time.
 */
const vazirmatn = localFont({
  src: "../fonts/Vazirmatn.woff2",
  weight: "100 900",
  display: "swap",
  variable: "--font-sans",
  // Tahoma shapes Persian correctly and is on every Windows machine in Iran,
  // so the swap lands on something readable rather than on a fallback that
  // renders Persian as disconnected letterforms.
  fallback: ["Tahoma", "Segoe UI", "system-ui", "sans-serif"],
  adjustFontFallback: false,
});

export const metadata = {
  title: "میترا · Mithra",
  description:
    "AI-powered panoramic vision platform for intelligent asset detection and street inventory",
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
  // Stamped into the HTML so the client knows which build it is running.
  const buildId = await currentBuildId();
  const isFa = locale === "fa";

  return (
    <html
      lang={locale}
      dir={isFa ? "rtl" : "ltr"}
      data-theme="dark"
      className={vazirmatn.variable}
      suppressHydrationWarning
    >
      <head>
        <meta name="bina-build" content={buildId} />
        {/* Applied before paint so a stored light preference never flashes dark. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('bina-theme');if(t){document.documentElement.dataset.theme=t}}catch(e){}`,
          }}
        />
      </head>
      <body>
        <StaleBuildRecovery buildId={buildId} />
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
