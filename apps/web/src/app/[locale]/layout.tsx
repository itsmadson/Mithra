import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import "maplibre-gl/dist/maplibre-gl.css";
import "../globals.css";

export const metadata = {
  title: "Bina — بینا",
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
  return (
    <html lang={locale} dir={locale === "fa" ? "rtl" : "ltr"}>
      <body>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
