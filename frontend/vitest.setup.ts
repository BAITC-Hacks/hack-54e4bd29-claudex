import "@testing-library/jest-dom/vitest";

// Значения публичной конфигурации для тестов.
process.env.NEXT_PUBLIC_API_BASE_URL ??= "/api/v1";
process.env.NEXT_PUBLIC_APP_ENV ??= "local";
