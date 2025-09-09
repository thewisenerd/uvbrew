import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import click
import tomllib
import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

indent = 2 * " "

@dataclass
class Meta:
    name: str
    version: str
    requires_python: str

    description: str | None
    homepage: str | None


@dataclass
class Package:
    name: str
    url: str
    sha256: str | None

def _packages(root: Path) -> Generator[Package, None, None]:
    output = subprocess.check_output([
        "uv",
        "export",
        "--format", "pylock.toml",
        "--no-dev"
    ], cwd=root)

    packages = tomllib.loads(output.decode())['packages']
    for package in packages:
        name = package['name']
        if not 'sdist' in package:
            logger.warning("sdist not found, skipping package", package=name)
            continue
        sdist = package['sdist']
        url = sdist['url']
        hashes = sdist['hashes']
        sha256 = hashes.get('sha256', None)

        yield Package(name=name, url=url, sha256=sha256)

def _meta(root: Path) -> Meta:
    project_path = root / "pyproject.toml"
    if not project_path.exists():
        raise FileNotFoundError("pyproject.toml not found")

    with project_path.open("rb") as f:
        pyproject = tomllib.load(f)

    project = pyproject.get("project", {})
    name: str | None = project.get("name", None)
    if name is None:
        raise ValueError("project.name not found in pyproject.toml")

    version: str | None = project.get("version", None)
    if version is None:
        raise ValueError("project.version not found in pyproject.toml")

    description = project.get("description", None)
    urls = project.get("urls", {})
    homepage = urls.get("Homepage", None)

    requires_python: str | None = project.get("requires-python", None)
    if requires_python is None:
        raise ValueError("project.requires-python not found in pyproject.toml")

    if not requires_python.startswith(">=3."):
        raise ValueError("requires-python must be >=3.x")

    return Meta(name=name, version=version, requires_python=requires_python.removeprefix(">="), description=description, homepage=homepage)

@click.command()
def cli():
    root = Path()

    lock_path = root / "uv.lock"
    if not lock_path.exists():
        click.echo("No uv.lock file found. Are you in a uv managed project?")
        raise click.Abort()

    meta = _meta(root)
    class_name = meta.name.capitalize()
    print(f"class {class_name} < Formula")
    print(indent + f'  include Language::Python::Virtualenv')
    print()

    if meta.description:
        print(indent + f"desc \"{meta.description}\"")
    if meta.homepage:
        print(indent + f"homepage \"{meta.homepage}\"")

    dist = root / "dist" / f"{meta.name}-{meta.version}.tar.gz"
    if not dist.exists():
        logger.info("building dist", root=root)
        subprocess.check_output(["uv", "build"], cwd=root)
        if not dist.exists():
            raise FileNotFoundError(f"dist file not found after build: {dist}")

    sha256 = hashlib.sha256()
    with open(dist, "rb") as f:
        sha256.update(f.read())

    print(indent + f"url \"file://{dist.resolve()}\"")
    print(indent + f"sha256 \"{sha256.hexdigest()}\"")
    print()

    print(indent + f"depends_on \"python@{meta.requires_python}\"")
    print()

    for pkg in _packages(root):
        print(indent + f"resource \"{pkg.name}\" do")
        print(indent*2 + f"url \"{pkg.url}\"")
        if pkg.sha256:
            print(indent*2 + f"sha256 \"{pkg.sha256}\"")
        print(indent + "end")
        print()

    print(indent + "def install")
    print(indent*2 + "virtualenv_install_with_resources")
    print(indent + "end")
    print()

    print(indent + "test do")
    print(indent*2 + f"system \"{meta.name}\", \"--version\"")
    print(indent + "end")

    print("end")
