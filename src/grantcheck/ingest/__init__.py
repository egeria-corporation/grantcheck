"""Index construction. NOT on the runtime path.

A user running ``uvx grantcheck`` must never install this subpackage's dependencies. It
runs in GitHub Actions monthly to build and publish the sharded index that the runtime
downloads. See ``prompts/01-build-core.md`` section 6.
"""
