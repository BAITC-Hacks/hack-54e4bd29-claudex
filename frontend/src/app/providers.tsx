"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/services/api-client";

/**
 * Клиент запросов создаётся в состоянии компонента, а не в области модуля:
 * при отрисовке на сервере общий на процесс клиент делил бы кэш
 * между пользователями.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // Повторять запрос при отказе аутентификации бессмысленно
              // и вредно: это выглядит как перебор.
              if (error instanceof ApiError && error.isUnauthenticated) {
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
