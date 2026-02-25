# Contributing to Teiken Claw

We welcome contributions from the community! Please follow these guidelines to ensure a smooth contribution process.

## Development Workflow

1. **Fork the repository**
2. **Create a feature branch** from `develop`:
   ```bash
   git checkout -b feat/your-feature-name develop
   ```
3. **Make your changes** following our coding standards
4. **Add tests** for new functionality
5. **Update documentation** if necessary
6. **Commit your changes** using conventional commits:
   ```
   feat(scope): add new feature
   fix(scope): fix bug
   docs(scope): update documentation
   refactor(scope): refactor code
   test(scope): add tests
   chore(scope): maintenance tasks
   ```
7. **Push to your fork** and submit a pull request to `develop`

## Code Standards

- **Python**: Follow PEP 8 style guidelines
- **Type Hints**: Use type hints for all function signatures
- **Testing**: Write unit tests for new functionality
- **Documentation**: Update docstrings and README as needed
- **Security**: Follow security best practices

## Branch Strategy

- `main`: Production-ready code
- `develop`: Integration branch for new features
- `feature/*`: Feature branches
- `fix/*`: Bug fix branches

## Testing

Run tests with:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Code Quality

We use the following tools for code quality:
- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking

## Security

- Never commit secrets or API keys
- Use environment variables for configuration
- Follow principle of least privilege
- Validate all user inputs

## Documentation

- Update README.md for user-facing changes
- Add API documentation in docs/
- Update inline documentation

## Pull Request Process

1. Ensure all tests pass
2. Ensure code follows style guidelines
3. Add a clear description of changes
4. Reference any related issues
5. Request review from maintainers

## Release Process

Releases are created from the `main` branch:
1. Merge `develop` into `main`
2. Create release branch
3. Update version number
4. Update changelog
5. Tag release
6. Publish to PyPI

## Getting Help

- Check existing issues before creating new ones
- Provide detailed bug reports
- Include reproduction steps
- Share relevant logs

## Community Guidelines

- Be respectful and constructive
- Follow the code of conduct
- Help other contributors
- Share knowledge

## License

By contributing, you agree that your contributions will be licensed under the MIT License.