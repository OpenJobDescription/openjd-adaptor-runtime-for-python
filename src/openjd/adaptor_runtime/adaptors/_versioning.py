# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import re

from functools import total_ordering
from typing import Any, NamedTuple

VERSION_RE = re.compile(r"^\d*\.\d*$")


@total_ordering
class SemanticVersion(NamedTuple):
    major: int
    minor: int

    def __str__(self):
        return f"{self.major}.{self.minor}"

    def __lt__(self, other: Any):
        if not isinstance(other, SemanticVersion):
            raise TypeError(f"Cannot compare SemanticVersion with {type(other)}")
        if self.major < other.major:
            return True
        elif self.major == other.major:
            if self.minor < other.minor:
                return True
        return False

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, SemanticVersion):
            raise TypeError(f"Cannot compare SemanticVersion with {type(other).__name__}")
        return self.major == other.major and self.minor == other.minor

    def has_compatibility_with(self, other: "SemanticVersion") -> bool:
        """
        Returns a boolean representing if the version of self has compatibility with other.

        This check is NOT commutative.
        """
        if not isinstance(other, SemanticVersion):
            raise TypeError(
                f"Cannot check compatibility of SemanticVersion with {type(other).__name__}"
            )
        if self.major == other.major == 0:
            return self.minor == other.minor  # Pre-release versions treat minor as breaking
        return self.major == other.major and self.minor >= other.minor

    @classmethod
    def parse(cls, version_str: str) -> "SemanticVersion":
        """
        Parses a version string into a SemanticVersion object.

        Raises ValueError if the version string is not valid.
        """
        try:
            if not VERSION_RE.match(version_str):
                raise ValueError
            major_str, minor_str = version_str.split(".")
            major = int(major_str)
            minor = int(minor_str)
        except ValueError:
            raise ValueError(f'Provided version "{version_str}" was not of form Major.Minor')
        return SemanticVersion(major, minor)
