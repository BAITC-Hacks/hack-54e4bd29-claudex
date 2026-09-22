/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone: минимальный образ для эксплуатации без node_modules целиком.
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return process.env.PILOT_API_URL ? [{source: "/api/pilot/:path*", destination: `${process.env.PILOT_API_URL}/api/pilot/:path*`}] : [];
  },
  // Версия и заголовок сервера наружу не сообщаются.
  poweredByHeader: false,
  // Проверка типов остаётся частью сборки: ошибка типов должна
  // ломать сборку, а не доезжать до эксплуатации.
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
