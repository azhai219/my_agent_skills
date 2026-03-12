---
name: setup_dev
description: "Use when you need to set up a regular Linux development environment with zsh + oh-my-zsh, Neovim (AppImage), AstroNvim config, and gdb-dashboard."
compatibility: Ubuntu or Debian-based Linux with apt, git, wget, and python3/pip.
---

# Setup Regular Dev Environment

Use this skill to set up the baseline development environment on a fresh Linux machine.

## Scope

1. zsh and oh-my-zsh
2. neovim in `~/soft/nvim`
3. gdb dashboard

## Run Order

Run the following sections in order.

## 1) zsh and oh-my-zsh

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

## Notes

- This setup appends aliases and shell snippets. Avoid running the same append commands many times to prevent duplicate lines.
- Blob of shell profile files can vary by team; if there is an existing dotfiles repo, prefer team conventions.