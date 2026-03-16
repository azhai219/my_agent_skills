#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence


class SetupError(RuntimeError):
    pass


class Context:
    def __init__(self) -> None:
        self.home = Path.home()
        self.env = os.environ.copy()
        self.nvim_version = self.env.get("SETUP_DEV_NVIM_VERSION", "v0.11.0")
        self.nvim_dir = Path(self.env.get("SETUP_DEV_NVIM_DIR", str(self.home / "soft" / "nvim"))).expanduser()
        self.astronvim_repo = self.env.get(
            "SETUP_DEV_ASTRONVIM_REPO", "https://github.com/alanzhai219/template.git"
        )
        self.astronvim_dir = Path(
            self.env.get("SETUP_DEV_ASTRONVIM_DIR", str(self.home / ".config" / "nvim"))
        ).expanduser()
        self.reextract_nvim = self.env.get("SETUP_DEV_REEXTRACT_NVIM", "0") == "1"

    def log(self, message: str) -> None:
        print(f"[setup-dev] {message}")

    def warn(self, message: str) -> None:
        print(f"[setup-dev] WARN: {message}", file=sys.stderr)

    def run(self, command: Sequence[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        self.log("Running: " + " ".join(command))
        result = subprocess.run(
            list(command),
            check=False,
            cwd=str(cwd) if cwd else None,
            env=self.env,
            text=True,
        )
        if check and result.returncode != 0:
            raise SetupError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
        return result

    def require_commands(self, *commands: str) -> None:
        missing = [command for command in commands if shutil.which(command) is None]
        if missing:
            raise SetupError(f"Required command not found: {', '.join(missing)}")

    def ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def append_line_if_missing(self, path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            current_text = path.read_text(encoding="utf-8")
            existing_lines = current_text.splitlines()
            if line in existing_lines:
                return
        else:
            current_text = ""
        with path.open("a", encoding="utf-8") as handle:
            if current_text and not current_text.endswith("\n"):
                handle.write("\n")
            handle.write(f"{line}\n")

    def append_block_if_missing(self, path: Path, marker: str, block: str) -> None:
        start = f"# >>> {marker} >>>"
        end = f"# <<< {marker} <<<"
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if start in current:
            return
        new_block = f"\n{start}\n{block}\n{end}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(new_block)

    def replace_or_append_line(self, path: Path, pattern: str, replacement: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        regex = re.compile(pattern)
        replaced = False
        updated: list[str] = []
        for line in lines:
            if regex.match(line):
                updated.append(replacement)
                replaced = True
            else:
                updated.append(line)
        if not replaced:
            updated.append(replacement)
        path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    def ensure_download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self.log(f"File already present: {destination}")
            return
        self.log(f"Downloading {url} -> {destination}")
        urllib.request.urlretrieve(url, str(destination))

    def ensure_git_clone(self, repo_url: str, target_dir: Path) -> None:
        self.require_commands("git")
        if (target_dir / ".git").is_dir():
            self.log(f"Repository already present: {target_dir}")
            return
        if target_dir.exists():
            raise SetupError(f"Target path exists and is not a git repository: {target_dir}")
        self.run(["git", "clone", "--depth", "1", repo_url, str(target_dir)])

    def sudo_apt_install(self, *packages: str) -> None:
        self.require_commands("sudo", "apt")
        self.run(["sudo", "apt", "update"])
        self.run(["sudo", "apt", "install", "-y", *packages])


class SetupModule(ABC):
    name: str = ""
    order: int = 0

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError


class ZshModule(SetupModule):
    name = "zsh"
    order = 10

    def run(self) -> None:
        self.ctx.sudo_apt_install("zsh")
        self.ctx.append_block_if_missing(
            self.ctx.home / ".bashrc",
            "setup-dev-auto-enter-zsh",
            '[ -z "$PS1" ] && return\ntest -f /usr/bin/zsh && exec /usr/bin/zsh',
        )
        self.ctx.log("zsh setup completed")


class OhMyZshModule(SetupModule):
    name = "oh_my_zsh"
    order = 20

    def run(self) -> None:
        self.ctx.ensure_git_clone("https://github.com/ohmyzsh/ohmyzsh.git", self.ctx.home / ".oh-my-zsh")

        zshrc = self.ctx.home / ".zshrc"
        if not zshrc.exists():
            shutil.copy(self.ctx.home / ".oh-my-zsh" / "templates" / "zshrc.zsh-template", zshrc)

        plugin_dir = Path(
            self.ctx.env.get(
                "ZSH_CUSTOM", str(self.ctx.home / ".oh-my-zsh" / "custom")
            )
        ) / "plugins" / "zsh-autosuggestions"
        self.ctx.ensure_git_clone("https://github.com/zsh-users/zsh-autosuggestions.git", plugin_dir)

        self.ctx.replace_or_append_line(zshrc, r"^plugins=", "plugins=(git zsh-autosuggestions)")
        self.ctx.replace_or_append_line(zshrc, r'^ZSH_THEME=', 'ZSH_THEME="gnzh"')
        self.ctx.log("oh-my-zsh setup completed")


class NvimModule(SetupModule):
    name = "nvim"
    order = 30

    def run(self) -> None:
        appimage_name = "nvim-linux-x86_64.appimage"
        appimage_path = self.ctx.nvim_dir / appimage_name
        extracted_nvim = self.ctx.nvim_dir / "squashfs-root" / "usr" / "bin" / "nvim"

        self.ctx.ensure_download(
            f"https://github.com/neovim/neovim/releases/download/{self.ctx.nvim_version}/{appimage_name}",
            appimage_path,
        )
        appimage_path.chmod(0o755)

        if self.ctx.reextract_nvim or not extracted_nvim.exists():
            squashfs_root = self.ctx.nvim_dir / "squashfs-root"
            if squashfs_root.exists():
                shutil.rmtree(squashfs_root)
            self.ctx.run([str(appimage_path), "--appimage-extract"], cwd=self.ctx.nvim_dir)

        alias_target = str(extracted_nvim)
        self.ctx.append_line_if_missing(self.ctx.home / ".bashrc", f"alias vi={alias_target}")
        self.ctx.append_line_if_missing(self.ctx.home / ".zshrc", f"alias vi={alias_target}")
        self.ctx.append_line_if_missing(self.ctx.home / ".bashrc", f"alias nvim={alias_target}")
        self.ctx.append_line_if_missing(self.ctx.home / ".zshrc", f"alias nvim={alias_target}")

        self.ctx.run([alias_target, "--version"], check=True)
        self.ctx.log("neovim setup completed")


class AstroNvimModule(SetupModule):
    name = "astronvim"
    order = 40

    def run(self) -> None:
        if (self.ctx.astronvim_dir / ".git").is_dir():
            current_remote = subprocess.run(
                ["git", "-C", str(self.ctx.astronvim_dir), "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
                text=True,
                env=self.ctx.env,
            ).stdout.strip()
            if current_remote == self.ctx.astronvim_repo:
                self.ctx.run(["git", "-C", str(self.ctx.astronvim_dir), "pull", "--ff-only"])
                self.ctx.log("AstroNvim template updated")
                return
            self.ctx.warn(
                f"Skipping AstroNvim template because {self.ctx.astronvim_dir} already points to {current_remote}"
            )
            return

        if self.ctx.astronvim_dir.exists():
            self.ctx.warn(f"Skipping AstroNvim template because target already exists: {self.ctx.astronvim_dir}")
            return

        self.ctx.ensure_git_clone(self.ctx.astronvim_repo, self.ctx.astronvim_dir)
        self.ctx.log("AstroNvim template setup completed")


class GdbDashboardModule(SetupModule):
    name = "gdb_dashboard"
    order = 50

    def run(self) -> None:
        self.ctx.sudo_apt_install("gdb")
        self.ctx.ensure_download(
            "https://github.com/cyrus-and/gdb-dashboard/raw/master/.gdbinit",
            self.ctx.home / ".gdbinit",
        )

        pip_executable = shutil.which("pip")
        if pip_executable:
            self.ctx.run([pip_executable, "install", "--user", "pygments"])
        else:
            self.ctx.run([sys.executable, "-m", "pip", "install", "--user", "pygments"])
        self.ctx.log("gdb dashboard setup completed")


class VerifyModule(SetupModule):
    name = "verify"
    order = 60

    def run(self) -> None:
        self.ctx.require_commands("zsh", "gdb")
        nvim_bin = self.ctx.nvim_dir / "squashfs-root" / "usr" / "bin" / "nvim"

        self.ctx.run(["zsh", "--version"])
        print(f"login shell: {self.ctx.env.get('SHELL', 'unknown')}")
        if nvim_bin.exists():
            self.ctx.run([str(nvim_bin), "--version"])
        else:
            self.ctx.warn(f"Neovim binary not found at {nvim_bin}")
        self.ctx.run(["gdb", "--version"])
        self.ctx.log("verification completed")


MODULE_TYPES = sorted(SetupModule.__subclasses__(), key=lambda cls: cls.order)
MODULE_INDEX = {module_type.name: module_type for module_type in MODULE_TYPES}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set up a Linux development environment.")
    parser.add_argument("modules", nargs="*", help="Modules to run. Defaults to all modules.")
    parser.add_argument("--list", action="store_true", help="List available modules and exit.")
    return parser


def resolve_modules(requested: Sequence[str]) -> list[str]:
    if not requested:
        return [module_type.name for module_type in MODULE_TYPES]
    unknown = [name for name in requested if name not in MODULE_INDEX]
    if unknown:
        raise SetupError(f"Unknown module(s): {', '.join(unknown)}")
    return list(requested)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        for module_type in MODULE_TYPES:
            print(module_type.name)
        return 0

    ctx = Context()
    selected_modules = resolve_modules(args.modules)
    for module_name in selected_modules:
        ctx.log(f"Running module: {module_name}")
        MODULE_INDEX[module_name](ctx).run()

    ctx.log("All requested modules completed")
    ctx.log("Open a new shell or source your shell rc files to pick up aliases and shell changes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupError as exc:
        print(f"[setup-dev] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
