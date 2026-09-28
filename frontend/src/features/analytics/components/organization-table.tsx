import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { withAnalyticsContext } from "@/features/analytics/navigation-context";
import { SuppressedValue } from "@/features/analytics/components/suppressed-value";
import type { AnalyticsQuery, Organization } from "@/features/analytics/types";

export function OrganizationTable({ items, context }: { items: Organization[]; context?: AnalyticsQuery }) {
  return <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm"><thead className="bg-muted/70 text-xs text-muted-foreground"><tr><th className="px-4 py-3">Организация</th><th className="px-4 py-3">Статус</th><th className="px-4 py-3 text-right">Направления</th><th className="px-4 py-3 text-right">Ожидающие</th><th className="px-4 py-3 text-right">Отказы</th></tr></thead><tbody>{items.map((item) => {
    const path = item.canonical_hospital_id ? `/hospitals/${item.canonical_hospital_id}` : `/organizations/${encodeURIComponent(item.organization_ref)}`;
    return <tr key={item.organization_ref} className="border-t"><td className="px-4 py-3"><Link className="font-medium text-primary hover:underline" href={withAnalyticsContext(path, context)}>{item.display_name || item.identity_label || "Без названия"}</Link><p className="mt-0.5 text-xs text-muted-foreground">{item.source_system}</p></td><td className="px-4 py-3"><Badge variant={item.mapping_status === "MAPPED" ? "success" : "neutral"}>{item.mapping_status === "MAPPED" ? "Сопоставлена" : "Не сопоставлена"}</Badge></td><td className="px-4 py-3 text-right"><SuppressedValue cell={item.referrals_total} /></td><td className="px-4 py-3 text-right"><SuppressedValue cell={item.waiting_records} /></td><td className="px-4 py-3 text-right"><SuppressedValue cell={item.refusals_total} /></td></tr>;
  })}</tbody></table></div>;
}

