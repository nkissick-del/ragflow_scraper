# Contributing to Multi-Site PDF Scraper

Thank you for your interest in contributing to the Multi-Site PDF Scraper! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Submitting Changes](#submitting-changes)

## Code of Conduct

This project is committed to providing a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Git

### Setting Up Development Environment

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ragflow_scraper.git
   cd ragflow_scraper
   ```

2. Set up the development environment:
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Build and start dev containers
   make dev-build
   make dev-up
   ```

3. Verify the setup:
   ```bash
   # Run tests
   make test
   
   # Access dev UI at http://localhost:5001
   ```

For detailed setup instructions, see [DEVELOPER_GUIDE.md](docs/development/DEVELOPER_GUIDE.md).

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `copilot/*` - Feature branches (created by AI agents)
- Create feature branches from `main`

### Making Changes

1. Create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following our [coding standards](#coding-standards)

3. Write tests for your changes

4. Run the test suite:
   ```bash
   make test
   ```

5. Commit your changes with clear, descriptive messages:
   ```bash
   git commit -m "feat: add new scraper for example.com"
   ```

### Commit Message Convention

Follow conventional commit format:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions or modifications
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

## Coding Standards

### Python Style

- Follow PEP 8 style guide
- Use Ruff for linting and formatting
- Maximum line length: 100 characters
- Use type hints where appropriate

### Running Linters

```bash
# In dev container
docker exec scraper-app ruff check .
docker exec scraper-app ruff format --check .
```

### Code Quality

- Write clear, self-documenting code
- Add docstrings to public functions and classes
- Keep functions focused and small
- Avoid unnecessary complexity

## Testing

### Test Requirements

- All new features must include unit tests
- Bug fixes should include regression tests
- Maintain or improve code coverage

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests
make test-int

# Specific test file
make test-file FILE=tests/unit/test_example.py
```

### Test Organization

- `tests/unit/` - Fast, isolated unit tests
- `tests/integration/` - Tests requiring external services
- `tests/stack/` - End-to-end tests with full stack (excluded by default)

## Documentation

### Documentation Standards

- Update documentation for user-facing changes
- Keep README.md up to date
- Add docstrings to new public APIs
- Update relevant guides in `docs/`

### Documentation Structure

- `docs/development/` - Developer guides and references
- `docs/operations/` - Deployment and operations
- `docs/reference/` - Technical specifications
- `docs/archive/` - Historical/deprecated documentation

See [DEVELOPER_GUIDE.md](docs/development/DEVELOPER_GUIDE.md) for detailed documentation standards.

## Submitting Changes

### Pull Request Process

1. Update documentation reflecting your changes
2. Ensure all tests pass
3. Update CHANGELOG.md if appropriate
4. Push your branch and create a pull request
5. Fill out the PR template with:
   - Description of changes
   - Related issue numbers
   - Testing performed
   - Any breaking changes

### PR Review

- At least one maintainer review is required
- All CI checks must pass
- Address review feedback promptly
- Keep PRs focused and reasonably sized

### After Merge

- Delete your feature branch
- Pull latest changes from main
- Thank the reviewers!

## Adding a New Scraper

New scrapers are a common contribution! See the detailed guide:

- [EXAMPLE_SCRAPER_WALKTHROUGH.md](docs/development/EXAMPLE_SCRAPER_WALKTHROUGH.md)

Quick checklist:

1. Create `app/scrapers/your_scraper.py` inheriting from `BaseScraper`
2. Implement required methods: `scrape()`, `get_metadata()`
3. Add configuration in `config/scrapers/your_scraper.json`
4. Write unit tests in `tests/unit/test_your_scraper.py`
5. Update scraper registry (auto-discovery handles this)
6. Test with `make test-file FILE=tests/unit/test_your_scraper.py`

## Getting Help

- **Documentation**: Check [docs/](docs/) for guides
- **Issues**: Search existing issues or create a new one
- **Discussions**: Use GitHub Discussions for questions

## Recognition

Contributors are recognized in:

- Git commit history
- Release notes
- Project acknowledgments

Thank you for contributing to make this project better!
