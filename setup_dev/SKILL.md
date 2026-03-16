---
name: setup_dev
description: "Use when you need to set up a regular Linux development environment with a reusable standalone Python script. Each setup module is a class in one file."
compatibility: Ubuntu or Debian-based Linux with apt, git, wget, and python3/pip.
---

# Setup Regular Dev Environment

Use this skill to set up the baseline development environment on a fresh Linux machine.

The setup logic is now extracted into a standalone Python script that can run without an agent:

- [script/setup_dev.py](script/setup_dev.py)

The script is modular and easy to extend:

- each module is a Python class in the same file
- the entry script keeps one registry of module classes
- adding a new module only requires adding one new class

## Scope

1. zsh and oh-my-zsh
2. neovim in `~/soft/nvim`
3. gdb dashboard

## Script Layout

- [script/setup_dev.py](script/setup_dev.py): standalone entrypoint and module definitions

Module classes in that file:

- `ZshModule`
- `OhMyZshModule`
- `NvimModule`
- `AstroNvimModule`
- `GdbDashboardModule`
- `VerifyModule`

## Recommended Usage

Run all modules:

```bash
python3 .github/setup_dev/script/setup_dev.py
```

Run selected modules only:

```bash
python3 .github/setup_dev/script/setup_dev.py zsh oh_my_zsh nvim
```

List available modules:

```bash
python3 .github/setup_dev/script/setup_dev.py --list
```

Optional environment overrides:

```bash
SETUP_DEV_NVIM_VERSION=v0.11.0 \
SETUP_DEV_NVIM_DIR="$HOME/soft/nvim" \
SETUP_DEV_ASTRONVIM_DIR="$HOME/.config/nvim" \
python3 .github/setup_dev/script/setup_dev.py
```

## Run Order

The default script order is:

1. `zsh`
2. `oh_my_zsh`
3. `nvim`
4. `astronvim`
5. `gdb_dashboard`
6. `verify`

This matches the manual process below.

## 1) zsh and oh-my-zsh

Equivalent modules: `zsh`, `oh_my_zsh`

### 1.1 Install zsh

```bash
sudo apt update
sudo apt install -y zsh
```

### 1.2 Auto-enter zsh from bash

Append the following lines to `~/.bashrc`:

```bash
cat <<'EOF' >> ~/.bashrc
[ -z "$PS1" ] && return
test -f /usr/bin/zsh && exec /usr/bin/zsh
EOF
```

### 1.3 Install oh-my-zsh

```bash
git clone https://github.com/ohmyzsh/ohmyzsh.git ~/.oh-my-zsh --depth 1
cp ~/.oh-my-zsh/templates/zshrc.zsh-template ~/.zshrc
```

### 1.4 Install useful plugin and update .zshrc

```bash
git clone https://github.com/zsh-users/zsh-autosuggestions.git "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions" --depth 1
```

Set plugins to:

```bash
plugins=(git zsh-autosuggestions)
```

Quick auto-update command for `~/.zshrc`:

```bash
sed -i 's/^plugins=.*/plugins=(git zsh-autosuggestions)/' ~/.zshrc
```

### 1.5 Update theme to `gnzh`

```bash
sed -i 's/^ZSH_THEME=.*/ZSH_THEME="gnzh"/' ~/.zshrc
```

Reload shell:

```bash
source ~/.zshrc
```

## 2) nvim

Equivalent modules: `nvim`, `astronvim`

### 2.1 Install neovim to `~/soft/nvim`

```bash
mkdir -p ~/soft/nvim
cd ~/soft/nvim
wget https://github.com/neovim/neovim/releases/download/v0.11.0/nvim-linux-x86_64.appimage
```

### 2.2 Make executable and extract

```bash
chmod +x ./nvim-linux-x86_64.appimage
./nvim-linux-x86_64.appimage --appimage-extract
./squashfs-root/usr/bin/nvim --version | head -n 1
```

### 2.3 Add alias

```bash
echo 'alias vi=~/soft/nvim/squashfs-root/usr/bin/nvim' >> ~/.bashrc
echo 'alias vi=~/soft/nvim/squashfs-root/usr/bin/nvim' >> ~/.zshrc
```

Optional:

```bash
echo 'alias nvim=~/soft/nvim/squashfs-root/usr/bin/nvim' >> ~/.bashrc
echo 'alias nvim=~/soft/nvim/squashfs-root/usr/bin/nvim' >> ~/.zshrc
```

### 2.4 Install AstroNvim template

```bash
git clone https://github.com/alanzhai219/template.git ~/.config/nvim
```

## 3) gdb

Equivalent modules: `gdb_dashboard`, `verify`

Install gdb dashboard and python dependency:

```bash
wget -P ~ https://github.com/cyrus-and/gdb-dashboard/raw/master/.gdbinit
pip install pygments
```

If `pip` is missing:

```bash
python3 -m pip install --user pygments
```

## Quick Verification

```bash
zsh --version
echo $SHELL
vi --version | head -n 1
gdb --version | head -n 1
```

## Extending the Script

To add a new setup step:

1. add a new class in [script/setup_dev.py](script/setup_dev.py)
2. subclass `SetupModule`
3. give it a unique `name` and `order`
4. implement `run()`
5. rerun [script/setup_dev.py](script/setup_dev.py)

Example module skeleton:

```python
class TmuxModule(SetupModule):
	name = "tmux"
	order = 70

	def run(self) -> None:
		print("install tmux here")
```

## Notes

- The standalone Python script is written to be idempotent for common reruns: it avoids duplicate aliases, avoids duplicating shell snippets, and skips or updates existing git clones where practical.
- This setup appends aliases and shell snippets. Avoid running the same append commands many times outside the script.
- Blob of shell profile files can vary by team; if there is an existing dotfiles repo, prefer team conventions.
- The script does not force-source your current shell session. Open a new shell or source your rc files after it completes.