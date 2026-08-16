import { redirect } from "next/navigation";

/**
 * The signs page became the inventory.
 *
 * It was built when the product only found road signs; it now holds seventy-one
 * kinds of thing, and "signs" was the wrong name for it long before the URL
 * changed. Anyone holding the old link is sent on rather than shown a 404.
 */
export default async function SignsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/inventory`);
}
