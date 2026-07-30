"""Application version.

CI overwrites __version__ with the release tag at build time (see
.github/workflows/build-release.yml), so the built exe and its mirror
source report the release they shipped in. Local builds report "dev".
"""
__version__ = "v1.0.8"
