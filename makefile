default: help

help:
	@echo "make [clean|bump-version|publish]"

clean:
	rm -rf dist/

bump-version:
	@test -z "$$(git status --porcelain)" || (echo "uncommitted changes found!" && exit 1)
	uv version --bump patch
	git add pyproject.toml uv.lock
	git commit -m "v$$(uv version --short)"

publish: clean
	@test -z "$$(git status --porcelain)" || (echo "uncommitted changes found!" && exit 1)
	uv build
	uv publish

.PHONY: default help clean publish
