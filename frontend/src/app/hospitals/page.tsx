"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { fetchAllOrganizations } from "@/features/analytics/api";
import { DEFAULT_ANALYTICS_QUERY, withAnalyticsContext } from "@/features/analytics/navigation-context";
import type { AnalyticsCell, Organization } from "@/features/analytics/types";
import { useRegions } from "@/hooks/use-domain";
import { fetchAllHospitals } from "@/services/domain";
import type { Hospital } from "@/types/domain";

type SortField = "name" | "code" | "region" | "status";
type Row = { hospital: Hospital; region: string; metrics?: Organization };

function metric(cell: AnalyticsCell | undefined): string {
  if (!cell) return "—";
  if (cell.suppressed) return "Скрыто";
  return cell.value === null ? "—" : cell.value.toLocaleString("ru-RU");
}

function SortHeader({ label, field, current, descending, onSort }: { label: string; field: SortField; current: SortField; descending: boolean; onSort: (field: SortField) => void }) {
  return <th className="whitespace-nowrap px-4 py-3"><button type="button" className="inline-flex items-center gap-1.5 hover:text-cyan-700" onClick={() => onSort(field)}>{label}{current === field ? descending ? <ArrowDown className="h-3 w-3" aria-hidden="true" /> : <ArrowUp className="h-3 w-3" aria-hidden="true" /> : null}</button></th>;
}

export default function HospitalsPage() {
  const { isAuthenticated } = useAuth();
  const directory = useQuery({ queryKey: ["hospitals", "all"], queryFn: ({ signal }) => fetchAllHospitals(signal), enabled: isAuthenticated });
  const regions = useRegions(isAuthenticated);
  const analytics = useQuery({
    queryKey: ["analytics", "organizations", DEFAULT_ANALYTICS_QUERY],
    queryFn: ({ signal }) => fetchAllOrganizations(DEFAULT_ANALYTICS_QUERY, signal),
    enabled: isAuthenticated,
  });
  const [search, setSearch] = useState("");
  const [regionId, setRegionId] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<SortField>("name");
  const [descending, setDescending] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const rows = useMemo<Row[]>(() => {
    const regionNames = new Map(regions.data?.items.map((region) => [region.id, region.name]) ?? []);
    const metrics = new Map(
      analytics.data?.data.items.filter((item) => item.canonical_hospital_id)
        .map((item) => [item.canonical_hospital_id, item] as const) ?? [],
    );
    const needle = search.trim().toLocaleLowerCase("ru-RU");
    return (directory.data?.items ?? [])
      .map((hospital) => ({ hospital, region: regionNames.get(hospital.region_id) ?? "Регион не указан", metrics: metrics.get(hospital.id) }))
      .filter(({ hospital, region }) =>
        (!regionId || hospital.region_id === regionId) &&
        (!status || (status === "active") === hospital.is_active) &&
        (!needle || `${hospital.name} ${hospital.code} ${region}`.toLocaleLowerCase("ru-RU").includes(needle)),
      )
      .sort((a, b) => {
        const value = (row: Row) => sort === "name" ? row.hospital.name : sort === "code" ? row.hospital.code : sort === "region" ? row.region : row.hospital.is_active ? "0" : "1";
        const comparison = value(a).localeCompare(value(b), "ru-RU", { numeric: true });
        return descending ? -comparison : comparison;
      });
  }, [directory.data, regions.data, analytics.data, search, regionId, status, sort, descending]);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, pages);
  const visible = rows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const start = rows.length ? (currentPage - 1) * pageSize + 1 : 0;
  const end = Math.min(currentPage * pageSize, rows.length);
  const changeSort = (field: SortField) => {
    if (sort === field) setDescending(!descending);
    else { setSort(field); setDescending(false); }
    setPage(1);
  };

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-cyan-700">Управление организациями</p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-[-0.045em] text-[#102f45]">Медицинские организации</h1>
          <p className="mt-1 text-sm leading-6 text-slate-600">Справочник организаций в вашей области доступа и подтверждённые исторические показатели.</p>
        </div>
        <div className="text-right text-xs text-slate-500"><span className="block">Всего доступно организаций</span><strong className="mt-0.5 block text-[28px] font-extrabold leading-none tracking-tight text-[#102f45]">{directory.data?.total.toLocaleString("ru-RU") ?? "—"}</strong></div>
      </section>

      <AuthGate>
        {(directory.isPending || regions.isPending) && <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">Загружаем справочник организаций…</p>}
        {(directory.isError || regions.isError) && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">Список организаций временно недоступен. Обновите страницу позже.</p>}
        {directory.data && regions.data && (
          <>
            <section className="grid gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm md:grid-cols-[minmax(230px,1.5fr)_minmax(160px,1fr)_minmax(160px,1fr)_auto] md:items-center">
              <label className="flex h-11 items-center gap-2 rounded-lg border border-slate-200 px-3 text-slate-500 focus-within:border-cyan-600">
                <Search className="h-4 w-4 shrink-0" aria-hidden="true" /><span className="sr-only">Поиск по названию, коду или региону</span>
                <input className="w-full min-w-0 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Название, код или регион" />
              </label>
              <label className="flex h-11 items-center rounded-lg border border-slate-200 px-3 focus-within:border-cyan-600"><span className="sr-only">Регион</span>
                <select className="w-full bg-transparent text-sm text-slate-800 outline-none" value={regionId} onChange={(event) => { setRegionId(event.target.value); setPage(1); }}>
                  <option value="">Все регионы</option>{regions.data.items.map((region) => <option key={region.id} value={region.id}>{region.name}</option>)}
                </select>
              </label>
              <label className="flex h-11 items-center gap-2 rounded-lg border border-slate-200 px-3 text-slate-500 focus-within:border-cyan-600"><SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden="true" /><span className="sr-only">Статус организации</span>
                <select className="w-full bg-transparent text-sm text-slate-800 outline-none" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
                  <option value="">Все статусы</option><option value="active">Активна</option><option value="inactive">Неактивна</option>
                </select>
              </label>
              <button type="button" className="h-11 px-3 text-xs font-bold text-cyan-700 hover:text-cyan-900 hover:underline" onClick={() => { setSearch(""); setRegionId(""); setStatus(""); setPage(1); }}>Сбросить фильтры</button>
            </section>

            {analytics.isError && <p className="text-xs text-amber-800">Исторические показатели временно недоступны; справочник остаётся доступным.</p>}
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="Список медицинских организаций">
              <div className="overflow-x-auto"><table className="w-full min-w-[920px] text-left text-xs text-slate-700">
                <thead className="bg-[#edf3f6] text-[11px] font-semibold text-slate-600"><tr>
                  <SortHeader label="Наименование организации" field="name" current={sort} descending={descending} onSort={changeSort} />
                  <SortHeader label="Код" field="code" current={sort} descending={descending} onSort={changeSort} />
                  <SortHeader label="Регион" field="region" current={sort} descending={descending} onSort={changeSort} />
                  <th className="whitespace-nowrap px-4 py-3 text-right">Направления</th><th className="whitespace-nowrap px-4 py-3 text-right">Ожидающие</th><th className="whitespace-nowrap px-4 py-3 text-right">Отказы</th>
                  <SortHeader label="Статус" field="status" current={sort} descending={descending} onSort={changeSort} />
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {visible.map(({ hospital, region, metrics }) => <tr key={hospital.id} className="transition-colors hover:bg-cyan-50/40">
                    <td className="min-w-[245px] px-4 py-3 font-bold text-[#12334a]"><Link className="hover:text-cyan-700 hover:underline" href={withAnalyticsContext(`/hospitals/${hospital.id}`, DEFAULT_ANALYTICS_QUERY)}>{hospital.name}</Link></td>
                    <td className="px-4 py-3 tabular-nums">{hospital.code}</td><td className="min-w-[150px] px-4 py-3">{region}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{metric(metrics?.referrals_total)}</td><td className="px-4 py-3 text-right tabular-nums">{metric(metrics?.waiting_records)}</td><td className="px-4 py-3 text-right tabular-nums">{metric(metrics?.refusals_total)}</td>
                    <td className="px-4 py-3"><span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold ${hospital.is_active ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{hospital.is_active ? "Активна" : "Неактивна"}</span></td>
                  </tr>)}
                  {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-500">По выбранным фильтрам организации не найдены.</td></tr>}
                </tbody>
              </table></div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-xs text-slate-500">
                <span>Показано {start}–{end} из {rows.length}{rows.length !== directory.data.total ? ` (всего доступно ${directory.data.total})` : ""}</span>
                <div className="flex items-center gap-2">
                  <button type="button" aria-label="Предыдущая страница" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)} className="rounded-md p-2 hover:bg-slate-100 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
                  <span className="font-bold text-[#12334a]">{currentPage} / {pages}</span>
                  <button type="button" aria-label="Следующая страница" disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)} className="rounded-md p-2 hover:bg-slate-100 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
                  <label className="ml-2">Показывать по: <select className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-slate-700" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value={10}>10</option><option value={20}>20</option><option value={50}>50</option></select></label>
                </div>
              </div>
            </section>
            <p className="text-xs leading-5 text-slate-500">Направления и отказы — за период 1 января–31 марта 2025 года; «Ожидающие» — показатель из предоставленного снимка. «—» означает отсутствие сопоставленного значения. Даты обновления каждой организации API не предоставляет.</p>
          </>
        )}
      </AuthGate>
    </div>
  );
}
