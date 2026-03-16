# setup_dev script

This directory contains a standalone Python script for setting up a baseline Linux development environment.

Main script:

- [setup_dev.py](setup_dev.py)

## What it installs

The script currently supports these setup modules:

- `zsh`
- `oh_my_zsh`
- `nvim`
- `astronvim`
- `gdb_dashboard`
- `verify`

Default flow:

1. `zsh`
2. `oh_my_zsh`
3. `nvim`
4. `astronvim`
5. `gdb_dashboard`
6. `verify`

## Requirements

Target environment:

- Ubuntu or Debian-based Linux
- `python3`
- `sudo`
- `apt`
- `git`
- network access for downloading tools and repositories

The script also uses external commands depending on the module:

- `wget` is not required by the Python implementation
- `git` is required for `oh_my_zsh` and `astronvim`
- `apt` is required for `zsh` and `gdb_dashboard`

## Usage

Run all modules:

```bash
python3 setup_dev.py
```

List available modules:

```bash
python3 setup_dev.py --list
```

Run selected modules only:

```bash
python3 setup_dev.py zsh oh_my_zsh nvim
```

## Module details

### `zsh`

- installs `zsh` with `apt`
- appends a guarded block to `~/.bashrc` so interactive bash sessions auto-enter `zsh`

### `oh_my_zsh`

- clones `oh-my-zsh` into `~/.oh-my-zsh`
- initializes `~/.zshrc` from the template if missing
- installs `zsh-autosuggestions`
- updates `plugins=(git zsh-autosuggestions)`
- updates `ZSH_THEME="gnzh"`

### `nvim`

- downloads the Neovim AppImage into `~/soft/nvim` by default
- extracts the AppImage
- appends `vi` and `nvim` aliases into `~/.bashrc` and `~/.zshrc`

### `astronvim`

- clones the AstroNvim template repository into `~/.config/nvim` by default
- if the directory already points at the same remote, it runs `git pull --ff-only`
- if the directory exists with a different remote or is not a git repo, it skips with a warning

### `gdb_dashboard`

- installs `gdb` with `apt`
- downloads `.gdbinit` from `gdb-dashboard`
- installs `pygments` with `pip`

### `verify`

- checks `zsh`
- checks `gdb`
- checks extracted Neovim if present
- prints the current login shell from the environment

## Environment variables

The script supports these overrides:

- `SETUP_DEV_NVIM_VERSION`: Neovim release tag, default `v0.11.0`
- `SETUP_DEV_NVIM_DIR`: Neovim installation directory, default `~/soft/nvim`
- `SETUP_DEV_ASTRONVIM_REPO`: AstroNvim template repository URL
- `SETUP_DEV_ASTRONVIM_DIR`: AstroNvim config directory, default `~/.config/nvim`
- `SETUP_DEV_REEXTRACT_NVIM`: set to `1` to force re-extraction of the AppImage
- `ZSH_CUSTOM`: optional oh-my-zsh custom directory override

Example:

```bash
SETUP_DEV_NVIM_VERSION=v0.11.0 \
SETUP_DEV_NVIM_DIR="$HOME/soft/nvim" \
SETUP_DEV_ASTRONVIM_DIR="$HOME/.config/nvim" \
python3 setup_dev.py nvim astronvim
```

## Design

The implementation is intentionally kept in one file.

Core pieces in [setup_dev.py](setup_dev.py):

- `Context`: shared helpers for commands, downloads, file updates, and package installation
- `SetupModule`: base class for all modules
- one class per module
- a small registry built from subclasses of `SetupModule`

This keeps extension simple without introducing extra files.

## Extending

To add a new module:

1. open [setup_dev.py](setup_dev.py)
2. add a new subclass of `SetupModule`
3. define `name`
4. define `order`
5. implement `run()`

Example:

```python
class TmuxModule(SetupModule):
    name = "tmux"
    order = 70

    def run(self) -> None:
        self.ctx.sudo_apt_install("tmux")
```

The module will be picked up automatically because the registry is built from `SetupModule.__subclasses__()`.

## Notes

- The script is intended to be rerunnable.
- It avoids duplicate alias lines and duplicate shell blocks.
- It does not source shell rc files for the current session.
- After running it, open a new shell or source your rc files manually.
