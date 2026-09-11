/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone: минимальный образ для эксплуатации без node_modules целиком.
  output: "standalone",
  reactStrictMode: true,
  // Версия и заголовок сервера наружу не сообщаются.
  poweredByHeader: false,
  // Проверка типов остаётся частью сборки: ошибка типов должна
  // ломать сборку, а не доезжать до эксплуатации.
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
