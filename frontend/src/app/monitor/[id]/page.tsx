'use client';
import {use} from 'react';
import Link from 'next/link';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {pilotApi, number, day, severity, status} from '@/features/monitoring/api';
import type {Alert} from '@/features/monitoring/types';

export default function AlertPage({params}:{params:Promise<{id:string}>}) {
 const {id}=use(params); const client=useQueryClient();
 const query=useQuery({queryKey:['pilot-alert',id],queryFn:()=>pilotApi<Alert>(`alerts/${id}`),retry:1});
 const mutation=useMutation({mutationFn:(value:string)=>pilotApi<Alert>(`alerts/${id}`,'PATCH',{status:value}),onSuccess:data=>{client.setQueryData(['pilot-alert',id],data);void client.invalidateQueries({queryKey:['monitor']});}});
 const alert=query.data;
 if(query.error) return <p role="alert">{query.error.message} <Link href="/monitor">К предупреждениям</Link></p>;
 if(!alert) return <p>Загрузка предупреждения…</p>;
 return <div className="mx-auto max-w-4xl space-y-6"><Link className="text-sm text-teal-700" href="/monitor">← Все предупреждения</Link>
  <div><div className="mb-3 flex gap-3 text-xs font-medium"><span className="rounded-full bg-amber-100 px-3 py-1 text-amber-950">Критичность: {severity[alert.severity]}</span><span className="rounded-full bg-secondary px-3 py-1">{status[alert.status]}</span></div>
   <h1 className="text-3xl font-semibold">{alert.title}</h1><p className="mt-2 text-muted-foreground">{alert.hospital}</p><p className="mt-2 text-xs text-muted-foreground">Исторический прогноз на дату {day(alert.as_of)} · 7 дней</p>
   {alert.current_as_of!==alert.as_of && <p className="mt-3 text-sm text-amber-800">Воспроизведение уже перешло на другую дату. Эта карточка сохраняет исходный прогноз.</p>}</div>
  <section className="rounded-xl border bg-card p-6"><h2 className="text-lg font-semibold">Что происходит и почему это важно</h2><p className="mt-3">{alert.description}</p><p className="mt-3 text-sm text-muted-foreground">{alert.why_dangerous}</p><details className="mt-4 text-sm"><summary className="cursor-pointer font-medium">Почему сработало предупреждение</summary><p className="mt-2">{alert.trigger}</p></details></section>
  <section className="rounded-xl border bg-card p-6"><h2 className="text-lg font-semibold">Прогноз</h2><p className="mt-2 text-sm text-muted-foreground">Ожидается {number(alert.predicted_total)} направлений; обычная неделя — {number(alert.reference_total)}.</p>
   <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th className="py-2">Дата</th><th className="py-2">Направления, прогноз</th></tr></thead><tbody>{alert.forecast.map(p=><tr className="border-b last:border-0" key={p.date}><td className="py-2">{day(p.date)}</td><td className="py-2">{number(p.value)}</td></tr>)}</tbody></table></div>
   <p className="mt-3 text-xs text-muted-foreground">Дробные значения — математическое ожидание числа направлений.</p></section>
  <section className="rounded-xl border border-teal-200 bg-teal-50 p-6 text-teal-950"><h2 className="text-lg font-semibold">Что делать</h2><ol className="mt-4 space-y-5">{alert.actions.map((a,i)=><li key={a.owner}><p className="font-semibold">{i+1}. {a.owner} · {a.when}</p><p className="mt-1 text-sm">{a.text}</p><p className="mt-2 text-xs">Результат проверки: {a.check}</p></li>)}</ol><p className="mt-5 border-t border-teal-200 pt-3 text-xs">{alert.action_basis}</p><p className="mt-2 text-xs">{alert.effect}</p></section>
  <section className="rounded-xl border bg-card p-6"><h2 className="text-lg font-semibold">Насколько доверять этому прогнозу</h2><p className="mt-2 text-sm">{alert.quality.status==='SUPPORTED'?'На двух проверочных неделях по этой больнице модель точнее простого прогноза.':'На двух проверочных неделях по этой больнице модель не превзошла простой прогноз. Предупреждение экспериментальное.'}</p>
   <p className="mt-3 text-sm">Средняя ошибка: модель — <strong>{number(alert.quality.validation_ml.mae)}</strong> направления в день; простой прогноз — <strong>{number(alert.quality.validation_baseline.mae)}</strong>.</p>
   <p className="mt-2 text-sm">Максимальная ошибка недельной суммы на этих двух проверках: {number(alert.quality.weekly_error_max)}. Это наблюдавшаяся ошибка, не гарантированный интервал.</p>
   <Link className="mt-4 inline-block text-sm text-teal-700 underline" href="/monitor/model">Данные, обучение и независимая проверка →</Link></section>
  <div className="flex flex-wrap gap-3">{Object.entries(status).map(([value,label])=><button key={value} disabled={mutation.isPending || alert.status===value} onClick={()=>mutation.mutate(value)} className="rounded-lg border px-4 py-2 text-sm disabled:opacity-40">{label}</button>)}</div>
  {mutation.error && <p role="alert" className="text-red-700">{mutation.error.message}</p>}
 </div>;
}
