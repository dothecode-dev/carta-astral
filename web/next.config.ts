import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Imagen de producción autocontenida para el contenedor de Coolify.
  output: "standalone",

  async redirects() {
    // La raíz manda al idioma por defecto. Va acá y no en proxy.ts porque es un
    // redirect fijo que no necesita mirar la request: lo recomienda la doc de Next 16.
    return [{ source: "/", destination: "/es", permanent: false }];
  },
};

export default nextConfig;
