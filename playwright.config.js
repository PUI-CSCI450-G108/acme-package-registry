import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  use: {
    baseURL: 'http://localhost:8080',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'python3 -m http.server 8080 --directory .',
    url: 'http://localhost:8080',
    reuseExistingServer: true,
  },
});
