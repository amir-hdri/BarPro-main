const path = require("node:path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {
    root: path.dirname(__filename),
  },
};

module.exports = nextConfig;
