import { redirect } from "next/navigation";

export default function LocaleRoot({ params: { locale } }: { params: { locale: string } }) {
  redirect(`/${locale}/dashboard`);
}
