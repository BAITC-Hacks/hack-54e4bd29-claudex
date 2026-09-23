import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone: минимальный образ для эксплуатации без node_modules целиком.
  output: "standalone",
  reactStrictMode: true,
  turbopack: { root: projectRoot },
  async rewrites() {
    const localResearch = process.env.NEXT_PUBLIC_PILOT_MODE === "true" &&
      ["local", "test"].includes(process.env.NEXT_PUBLIC_APP_ENV) &&
      ["development", "test"].includes(process.env.NODE_ENV);
    return localResearch && process.env.PILOT_API_URL ? [{source: "/api/pilot/:path*", destination: `${process.env.PILOT_API_URL}/api/pilot/:path*`}] : [];
  },
  // Версия и заголовок сервера наружу не сообщаются.
  poweredByHeader: false,
  // Проверка типов остаётся частью сборки: ошибка типов должна
  // ломать сборку, а не доезжать до эксплуатации.
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
