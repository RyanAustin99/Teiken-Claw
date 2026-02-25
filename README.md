# Teiken Claw

Teiken Claw is a production-grade local-first AI agent platform designed for Windows environments. It provides a Telegram interface for interacting with AI agents that can perform various tasks including web search, file operations, code execution, and scheduled automation.

## Features

- **Local-First Architecture**: Runs entirely on your local machine
- **Telegram Interface**: Natural language interaction via Telegram bot
- **AI-Powered**: Integrates with Ollama for LLM and embeddings
- **Tool Ecosystem**: Web search, file operations, code execution, memory management
- **Scheduling**: Cron and interval job scheduling with APScheduler
- **Skills System**: YAML-defined skill workflows
- **Sub-Agents**: Hierarchical agent spawning with policy controls
- **Memory System**: Deterministic and LLM-powered memory with embeddings
- **Windows Integration**: PowerShell scripts and Windows service support

## Architecture

Teiken Claw follows a modular architecture with clear separation of concerns:

- **Core**: Database, queue, and logging foundation
- **Agent**: Runtime loop, tool calling, and context management
- **Interfaces**: Telegram bot and command system
- **Memory**: Session management, retrieval, and review
- **Tools**: Web, files, exec, memory, and scheduler tools
- **Scheduler**: Job scheduling and control state
- **Skills**: YAML-defined skill workflows
- **Sub-Agents**: Hierarchical agent spawning
- **Observability**: Health checks, audit logging, and admin APIs

## Quick Start (Windows)

### Prerequisites

- Python 3.11+ (download from python.org)
- Ollama (for AI capabilities) - download from ollama.ai
- Telegram Bot Token
- Windows 10/11

### Installation (PowerShell)

1. Clone the repository
2. Run the setup script:
   ```powershell
   .\scripts\setup.ps1
   ```
3. Edit `.env` and configure your settings
4. Start development:
   ```powershell
   .\scripts\run_dev.ps1
   ```

### Common Tasks

| Task | Command |
|------|---------|
| Run smoke tests | `.\scripts\smoke_test.ps1` |
| Create backup | `.\scripts\backup.ps1` |
| Install as service | `.\scripts\install_service.ps1` |
| Reset database | `.\scripts\reset_db.ps1 -Force` |
| Uninstall service | `.\scripts\install_service.ps1 -Uninstall` |

## Documentation

- [Specification](teiken_claw_spec.md)
- [Implementation Plan](teiken_claw_implementation_plan.md)
- [API Documentation](docs/api.md)
- [Configuration Guide](docs/config.md)

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
