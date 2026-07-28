import createMiddleware from "next-intl/middleware";
import { defaultLocale, locales } from "./i18n";

// Next 16 renamed the `middleware` file convention to `proxy`. next-intl still
// ships its handler under the old name; only the file convention changed.
export default createMiddleware({ locales, defaultLocale, localePrefix: "always" });

export const config = { matcher: ["/", "/(fa|en)/:path*"] };
