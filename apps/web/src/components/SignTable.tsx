"use client";

import { useTranslations } from "next-intl";
import { API_BASE, type Sign } from "../lib/api";

export default function SignTable({ signs }: { signs: Sign[] }) {
  const t = useTranslations();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-start">
            <th className="p-2"> </th>
            <th className="p-2 text-start">{t("table.class")}</th>
            <th className="p-2 text-start">{t("table.confidence")}</th>
            <th className="p-2 text-start">{t("table.location")}</th>
            <th className="p-2 text-start">{t("table.review")}</th>
          </tr>
        </thead>
        <tbody>
          {signs.map((sign) => (
            <tr key={sign.id} className="border-b">
              <td className="p-2">
                {sign.crop_url && (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    src={`${API_BASE}${sign.crop_url}`}
                    alt=""
                    className="h-10 w-10 rounded object-cover"
                  />
                )}
              </td>
              <td className="p-2">{t(`classes.${sign.sign_class}`)}</td>
              <td className="p-2">{(sign.confidence * 100).toFixed(0)}%</td>
              <td className="p-2 tabular-nums">
                {sign.lat.toFixed(5)}, {sign.lon.toFixed(5)}
              </td>
              <td className="p-2">{sign.needs_review ? "●" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
