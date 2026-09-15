import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

export default function HomePage() {
  return (
    <section className="mx-auto max-w-2xl py-16 text-center">
      <p className="text-sm font-medium text-primary">MedSignal</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">
        Система поддержки управленческих решений
      </h1>
      <p className="mt-4 text-muted-foreground">
        Ситуационный центр показывает проверенную описательную аналитику по
        направлениям, ожиданию и отказам с явным контекстом периода и качества
        данных.
      </p>
      <Link className={buttonVariants({ className: "mt-7" })} href="/dashboard">
        Открыть ситуационный центр
      </Link>
    </section>
  );
}
