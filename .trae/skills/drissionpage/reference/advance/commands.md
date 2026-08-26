# Command Line Interface
Main command: `dp`
## Commands
| Full Name | Short | Parameter | Description |
|-----------|-------|-----------|-------------|
| `--set-browser-path` | `-p` | Browser exe path | Set browser path in config. |
| `--set-user-path` | `-u` | User data folder path | Set user data path in config. |
| `--configs-to-here` | `-c` | (none) | Copy default ini to current folder. |
| `--launch-browser` | `-l` | Port number | Launch browser for the given port (0 uses config value). |
## Examples
```bash
dp -p "D:\chrome\Chrome.exe"
dp -u D:\chrome\user_data
dp -c
dp -l 9333
dp -l 0  # use port from config
```
