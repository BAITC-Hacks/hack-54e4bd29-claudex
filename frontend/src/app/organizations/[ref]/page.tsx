"use client";

import { useParams } from "next/navigation";

import { OrganizationAnalyticsView } from "@/features/analytics/components/organization-analytics-view";

export default function SourceOrganizationAnalyticsPage() {
  const { ref } = useParams<{ ref: string }>();
  return <OrganizationAnalyticsView organizationRef={decodeURIComponent(ref)} />;
}
