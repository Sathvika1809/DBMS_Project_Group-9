// The browser calls /api/*; Next proxies it to FastAPI, so there is no CORS
// setup in the browser. BACKEND_URL is read at BUILD time (see Dockerfile).
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

module.exports = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};
