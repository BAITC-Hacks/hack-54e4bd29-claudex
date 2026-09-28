"use client";

import { useParams } from "next/navigation";

import { OrganizationAnalyticsView } from "@/features/analytics/components/organization-analytics-view";

export default function HospitalAnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  return <OrganizationAnalyticsView organizationRef={`canonical:${id}`} />;
}
