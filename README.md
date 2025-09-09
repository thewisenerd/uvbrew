uvbrew
======

create homebrew formulae from a uv package.

uses `uv export --format=pylock.toml` with `--no-dev` as default.

## installation

```bash
uvx uvbrew
```

or, dog-fooding, [thewisenerd/homebrew-uvbrew](https://github.com/thewisenerd/homebrew-uvbrew)

```bash
brew tap thewisenerd/uvbrew
brew install uvbrew
```

## todo

- [ ] improve tests with `project.scripts` instead of `meta.name`
