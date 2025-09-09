import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import click
import httpx
import tomllib
import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

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

# from https://github.com/tdsmith/homebrew-pypi-poet/blob/fdafc615bcd28f29bcbe90789f07cc26f97c3bbc/poet/util.py#L1
def dash_to_studly(s):
    l = list(s)
    l[0] = l[0].upper()
    delims = "-_"
    for i, c in enumerate(l):
        if c in delims:
            if (i+1) < len(l):
                l[i+1] = l[i+1].upper()
    out = "".join(l)
    for d in delims:
        out = out.replace(d, "")
    return out

def _packages(root: Path, skip_packages: set[str]) -> Generator[Package, None, None]:
    output = subprocess.check_output([
        "uv",
        "export",
        "--format", "pylock.toml",
        "--no-dev"
    ], cwd=root)

    packages = tomllib.loads(output.decode())['packages']
    for package in packages:
        name = package['name']
        if name in skip_packages:
            continue

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

def _from_index(index_url: str, package: str, version: str) -> tuple[str, str] | None:
    log = logger.bind(package=package, version=version, index_url=index_url)
    r = httpx.get(f'{index_url}/{package}/json')
    if r.status_code == 404:
        log.warning(f"package not found")
        return None
    if r.status_code != 200:
        log.error("failed to fetch package metadata", status_code=r.status_code, response=r.text)
        return None

    log.debug("package metadata fetched")

    data = r.json()
    releases = data.get("releases", {})

    if version not in releases:
        log.warning("version not found")
        return None

    for idx, file in enumerate(releases[version]):
        url: str = file.get("url", "")
        if not url:
            log.debug("ignoring release with no url", index=idx)
        assert type(url) == str, f"url is not a string: {type(url)}"

        packagetype: str = file.get("packagetype", "")
        if packagetype != "":
            if packagetype != "sdist":
                log.debug("ignoring non-sdist release", index=idx, packagetype=packagetype)
                continue
        else:
            if url.endswith(".tar.gz"):
                log.debug("assuming sdist from url", index=idx, url=url)
            else:
                log.debug("ignoring non-sdist release", index=idx, url=url)
                continue

        sha256: str = file.get("digests", {}).get("sha256", None)
        if sha256 is None:
            log.debug("calculating sha256", index=idx, url=url)
            r = httpx.get(url)
            r.raise_for_status()
            sha256 = hashlib.sha256(r.content).hexdigest()
            log.debug("calculated sha256", sha256=sha256)

        return url, sha256

    logger.debug("package not found")
    return None

@click.command()
@click.option(
    '--indent-length', '-i', default=2, type=int, help='number of spaces to indent'
)
@click.option(
    '--index-url', '-I', default="https://pypi.org/pypi", type=str, help='custom package index url. must support the \'/json\' endpoint.'
)
@click.option(
    '-v', '--verbose', is_flag=True, help='enable verbose logging'
)
def cli(indent_length: int, index_url: str, verbose: bool):
    if verbose:
        logger.setLevel(logging.DEBUG)

    root = Path()
    indent = " " * indent_length

    lock_path = root / "uv.lock"
    if not lock_path.exists():
        click.echo("No uv.lock file found. Are you in a uv managed project?")
        raise click.Abort()

    meta = _meta(root)
    class_name = dash_to_studly(meta.name)
    print(f"class {class_name} < Formula")
    print(indent + f'include Language::Python::Virtualenv')
    print()

    if meta.description:
        print(indent + f"desc \"{meta.description}\"")
    if meta.homepage:
        print(indent + f"homepage \"{meta.homepage}\"")

    dist = root / "dist" / f"{meta.name}-{meta.version}.tar.gz"

    url, sha256 = _from_index(index_url, meta.name, meta.version) or (None, None)
    if not url:
        if not dist.exists():
            logger.info("building dist", root=root)
            subprocess.check_output(["uv", "build"], cwd=root)
            if not dist.exists():
                raise FileNotFoundError(f"dist file not found after build: {dist}")

        url = f"file://{dist.resolve()}"
        digest = hashlib.sha256()
        with open(dist, "rb") as f:
            digest.update(f.read())
        sha256 = digest.hexdigest()

    print(indent + f"url \"{url}\"")
    print(indent + f"sha256 \"{sha256}\"")
    print()

    print(indent + f"depends_on \"python@{meta.requires_python}\"")
    print()

    for pkg in _packages(root, {meta.name}):
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
