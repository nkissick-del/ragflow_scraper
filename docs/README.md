# Documentation Index

Welcome to the Multi-Site PDF Scraper documentation! This guide will help you navigate the documentation based on your role and needs.

## Quick Navigation

### 🚀 Getting Started

- **[Main README](../README.md)** - Project overview and quick start
- **[Deployment Guide](operations/DEPLOYMENT_GUIDE.md)** - Production deployment instructions
- **[Developer Guide](development/DEVELOPER_GUIDE.md)** - Development environment setup

### 👥 By Role

#### For End Users

- [Deployment Guide](operations/DEPLOYMENT_GUIDE.md) - How to deploy the application
- [Common Operations Runbook](operations/RUNBOOK_COMMON_OPERATIONS.md) - Day-to-day usage
- [Backend Migration Guide](operations/BACKEND_MIGRATION_GUIDE.md) - Switching between backends
- [Troubleshooting](operations/troubleshooting/) - Solutions to common issues

#### For Developers

- [Developer Guide](development/DEVELOPER_GUIDE.md) - Architecture and development setup
- [Example Scraper Walkthrough](development/EXAMPLE_SCRAPER_WALKTHROUGH.md) - Creating new scrapers
- [Backend Developer Guide](development/BACKEND_DEVELOPER_GUIDE.md) - Adding new backends
- [Error Handling](development/ERROR_HANDLING.md) - Exception patterns and logging
- [Logging and Error Standards](development/LOGGING_AND_ERROR_STANDARDS.md) - Logging best practices
- [Configuration & Services](development/CONFIG_AND_SERVICES.md) - Service architecture

#### For Operators/DevOps

- [Deployment Guide](operations/DEPLOYMENT_GUIDE.md) - Production deployment
- [Common Operations Runbook](operations/RUNBOOK_COMMON_OPERATIONS.md) - Operational procedures
- [Migration & State Repair](operations/MIGRATION_AND_STATE_REPAIR.md) - State management
- [Secrets Rotation](operations/SECRETS_ROTATION.md) - Security maintenance

#### For Contributors

- [CONTRIBUTING.md](../CONTRIBUTING.md) - How to contribute
- [Developer Guide](development/DEVELOPER_GUIDE.md) - Development guidelines
- [Example Scraper Walkthrough](development/EXAMPLE_SCRAPER_WALKTHROUGH.md) - Adding scrapers

## Documentation Structure

```
docs/
├── README.md                          # This file - documentation index
├── CHANGELOG.md                       # Version history and release notes
├── TODO.md                           # Roadmap and future plans
│
├── development/                      # Developer guides and references
│   ├── DEVELOPER_GUIDE.md            # Core development guide
│   ├── BACKEND_DEVELOPER_GUIDE.md    # Backend development
│   ├── EXAMPLE_SCRAPER_WALKTHROUGH.md # Step-by-step scraper creation
│   ├── CONFIG_AND_SERVICES.md        # Configuration architecture
│   ├── ERROR_HANDLING.md             # Error patterns and exceptions
│   └── LOGGING_AND_ERROR_STANDARDS.md # Logging best practices
│
├── operations/                       # Deployment and operations
│   ├── DEPLOYMENT_GUIDE.md           # Production deployment
│   ├── RUNBOOK_COMMON_OPERATIONS.md  # Day-to-day operations
│   ├── BACKEND_MIGRATION_GUIDE.md    # Backend switching guide
│   ├── MIGRATION_AND_STATE_REPAIR.md # State management
│   ├── SECRETS_ROTATION.md           # Security procedures
│   └── troubleshooting/              # Troubleshooting guides
│       └── ragflow_scraper_audit.md  # RAGFlow debugging
│
├── reference/                        # Technical specifications
│   └── METADATA_SCHEMA.md            # Document metadata format
│
├── archive/                          # Historical documentation
│   ├── README.md                     # Archive index
│   ├── plans/                        # Historical planning docs
│   └── jules/                        # Design explorations
│
└── screenshots/                      # Application screenshots
    └── current.png
```

## Documentation by Topic

### Architecture

- [Developer Guide - Architecture](development/DEVELOPER_GUIDE.md#architecture) - System overview
- [Config & Services](development/CONFIG_AND_SERVICES.md) - Service layer design
- [Backend Developer Guide](development/BACKEND_DEVELOPER_GUIDE.md) - Backend architecture

### Configuration

- [Config & Services](development/CONFIG_AND_SERVICES.md) - Configuration system
- [Deployment Guide - Environment Variables](operations/DEPLOYMENT_GUIDE.md#environment-variables)
- [Backend Migration Guide](operations/BACKEND_MIGRATION_GUIDE.md) - Backend configuration

### Scrapers

- [Example Scraper Walkthrough](development/EXAMPLE_SCRAPER_WALKTHROUGH.md) - Creating scrapers
- [Developer Guide - Scrapers](development/DEVELOPER_GUIDE.md#scrapers) - Scraper architecture
- [Error Handling](development/ERROR_HANDLING.md) - Error patterns

### Operations

- [Common Operations Runbook](operations/RUNBOOK_COMMON_OPERATIONS.md) - Daily operations
- [Deployment Guide](operations/DEPLOYMENT_GUIDE.md) - Deployment procedures
- [Migration & State Repair](operations/MIGRATION_AND_STATE_REPAIR.md) - State management
- [Secrets Rotation](operations/SECRETS_ROTATION.md) - Security maintenance

### Backends

- [Backend Developer Guide](development/BACKEND_DEVELOPER_GUIDE.md) - Creating backends
- [Backend Migration Guide](operations/BACKEND_MIGRATION_GUIDE.md) - Using different backends
- [Config & Services](development/CONFIG_AND_SERVICES.md) - Backend integration

### Testing

- [Developer Guide - Testing](development/DEVELOPER_GUIDE.md#testing) - Test strategy
- [Main README - Running Tests](../README.md#running-tests) - Test commands

### Security

- [SECURITY.md](../SECURITY.md) - Security policy and reporting
- [Secrets Rotation](operations/SECRETS_ROTATION.md) - Credential management
- [Deployment Guide - Security](operations/DEPLOYMENT_GUIDE.md#security) - Security best practices

### Troubleshooting

- [Common Operations Runbook](operations/RUNBOOK_COMMON_OPERATIONS.md#troubleshooting)
- [Troubleshooting Directory](operations/troubleshooting/) - Specific issues
- [Migration & State Repair](operations/MIGRATION_AND_STATE_REPAIR.md) - Recovery procedures

## Documentation Standards

### For Contributors

When adding or updating documentation:

1. **Placement**: Choose the appropriate directory (operations, development, reference)
2. **Linking**: Update this index when adding new documents
3. **Format**: Use Markdown with clear headings and examples
4. **Maintenance**: Update last-modified dates when making significant changes
5. **Audience**: Write for the intended audience (users, developers, operators)

### Style Guidelines

- Use clear, concise language
- Include code examples where helpful
- Provide both quick reference and detailed explanations
- Link to related documentation
- Keep documents focused on a single topic
- Use consistent formatting and structure

## Getting Help

Can't find what you're looking for?

1. **Search**: Use GitHub's search to find keywords
2. **Issues**: Check existing issues for discussions
3. **Create Issue**: Open a new issue if documentation is missing/unclear
4. **Contribute**: Submit a PR to improve documentation

## Recent Updates

See [CHANGELOG.md](CHANGELOG.md) for recent documentation changes and project updates.

## Archived Documentation

Historical planning documents and implementation notes are preserved in [archive/](archive/README.md). These may be outdated but are kept for historical context.

---

**Need something specific?** Use the navigation above or the search function to find what you need. If documentation is missing or unclear, please open an issue!
