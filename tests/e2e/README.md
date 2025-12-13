# Front-End E2E Tests

Basic automated tests for the ACME Package Registry front-end using Playwright.

## Running Tests

```bash
# Run all tests
npm run test:e2e
```

## Test Coverage

- **Authentication** (2 tests)
  - Login form validation
  - Logout functionality

- **Artifact Viewing** (2 tests)
  - Display artifact list
  - Open and close artifact detail modal

- **Search** (2 tests)
  - Search UI availability
  - Search input functionality

## Requirements

- Node.js 20+
- Chromium browser (installed automatically)

## CI/CD

Tests run automatically in GitHub Actions on every push and pull request.
