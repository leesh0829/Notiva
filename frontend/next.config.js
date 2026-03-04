const { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } = require("next/constants");

/**
 * Keep development and production build artifacts isolated on Windows.
 * This avoids intermittent missing chunk/module errors from stale .next state.
 */
module.exports = (phase) => {
  /** @type {import('next').NextConfig} */
  const base = {
    reactStrictMode: true,
  };

  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...base,
      distDir: ".next-dev",
      webpack: (config) => {
        config.cache = false;
        return config;
      },
    };
  }

  if (phase === PHASE_PRODUCTION_BUILD) {
    return {
      ...base,
      distDir: ".next-build",
    };
  }

  return base;
};
