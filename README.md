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

## Quick Start

### Prerequisites

- Python 3.11+
- Ollama (for AI capabilities)
- Telegram Bot Token
- Windows 10/11

### Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure
4. Run setup: `python scripts/setup.py`
5. Start development: `python scripts/run_dev.py`

## Documentation

- [Specification](teiken_claw_spec.md)
- [Implementation Plan](teiken_claw_implementation_plan.md)
- [API Documentation](docs/api.md)
- [Configuration Guide](docs/config.md)

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
