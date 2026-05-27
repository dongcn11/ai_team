# Claude Agent Configuration

This directory contains configuration files for the Claude AI assistant integration with this project.

## Files

- **`settings.json`** - Default agent permissions and capabilities (committed to repo)
  - Contains general permissions that apply across all development environments
  - Uses relative paths and generic patterns

- **`settings.local.json`** - Local/development-specific permissions (should NOT be committed)
  - Add this file to `.gitignore` (already done)
  - Contains sensitive or environment-specific permissions
  - Use this for local testing and development
  - **Do NOT commit secrets, API keys, or hardcoded paths**

- **`settings.template.json`** - Template for creating new `settings.local.json` files
  - Reference file for developers setting up their local environment
  - Shows recommended permissions and patterns
  - Copy to `settings.local.json` and customize as needed

## Setup Instructions

1. **Copy the template** (if you need custom local settings):
   ```bash
   cp .claude/settings.template.json .claude/settings.local.json
   ```

2. **Edit as needed**:
   - Use relative paths, not absolute paths
   - Avoid hardcoding environment-specific values
   - Remove debug/sensitive commands before committing

3. **Do NOT commit**:
   - `.claude/settings.json` if it contains local paths
   - `.claude/settings.local.json` (already in .gitignore)
   - Any files with hardcoded credentials or environment values

## Best Practices

✅ **DO:**
- Use relative paths: `Bash(git log ...)`
- Use wildcards: `*.js` instead of specific filenames
- Keep permissions minimal and secure
- Document custom permissions in comments

❌ **DON'T:**
- Hardcode absolute paths like `c:/www/ai_team_clean`
- Include sensitive commands that expose system internals
- Commit environment-specific configurations
- Add credentials or API endpoints
- Include debugging commands for production

## Common Issues

**Issue**: Settings.json has hardcoded paths
**Solution**: Use relative paths and wildcards instead

**Issue**: Settings.local.json is being committed
**Solution**: Make sure `.claude/settings.local.json` is in `.gitignore`

**Issue**: Agent can't access required tools
**Solution**: Check permissions in `settings.json` and add necessary capabilities

## Reference

For more information on Claude agent configuration, see the project's documentation or contact the development team.
