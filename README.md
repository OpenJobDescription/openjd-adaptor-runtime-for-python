# Open Job Description - Adaptor Runtime Library

[![pypi](https://img.shields.io/pypi/v/openjd-adaptor-runtime.svg?style=flat)](https://pypi.python.org/pypi/openjd-adaptor-runtime)
[![python](https://img.shields.io/pypi/pyversions/openjd-adaptor-runtime.svg?style=flat)](https://pypi.python.org/pypi/openjd-adaptor-runtime)
[![license](https://img.shields.io/pypi/l/openjd-adaptor-runtime.svg?style=flat)](https://github.com/OpenJobDescription/openjd-adaptor-runtime/blob/mainline/LICENSE)

This package provides a runtime library to help build application interfaces that simplify
Open Job Description job templates. When implemented by a third party on behalf of
an application, the result is a CLI command that acts as an adaptor. Application
developers can also implement support for these CLI patterns directly in their
applications, potentially using this library to simplify the work.

Interface features that this library can assist with include:

1. Run as a background daemon to amortize application startup and scene load time.
   * Tasks run in the context of [Open Job Description Sessions], and this pattern lets a
      scheduling engine sequentially dispatch tasks to a single process that retains the
      application, loaded scene, and any acceleration data structures in memory.
2. Report progress and status messages.
   * Applications write progress information and status messages in many different ways.
      An adaptor can scan the output of an application and report it in the format specified
      for [Open Job Description Stdout Messages].
3. Map file system paths in input data.
   * When running tasks on a different operating system, or when files are located at
      different locations compared to where they were at creation, an adaptor can take
      path mapping rules and perform [Open Job Description Path Mapping].
4. Transform signals like cancelation requests from the Open Job Description runtime into
   the signal needed by the application.
   * Applications may require different mechanisms to receive these messages, an adaptor
      can handle any differences with what Open Job Description provides to give full
      feature support.
5. Adjust application default behaviors for batch processing.
   * When running applications that were built for interactive use within a batch processing
      system, some default behaviors may lead to unreliability of workload completion, such
      as using watermarks when a license could not be acquired or returning a success exit
      code when an input data file could not be read. The adaptor can monitor and detect
      these cases.

[Open Job Description Sessions]: https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#sessions
[Open Job Description Stdout Messages]: https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#stdoutstderr-messages
[Open Job Description Path Mapping]: https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#path-mapping

Read the [Library Documentation](docs/README.md) to learn more.

## Compatibility

This library requires:

1. Python 3.9 or higher; and
2. Linux, MacOS, or Windows operating system.

## Versioning

This package's version follows [Semantic Versioning 2.0](https://semver.org/), but is still considered to be in its
initial development, thus backwards incompatible versions are denoted by minor version bumps. To help illustrate how
versions will increment during this initial development stage, they are described below:

1. The MAJOR version is currently 0, indicating initial development.
2. The MINOR version is currently incremented when backwards incompatible changes are introduced to the public API.
3. The PATCH version is currently incremented when bug fixes or backwards compatible changes are introduced to the public API.

## Downloading

You can download this package from:
- [PyPI](https://pypi.org/project/openjd-adaptor-runtime/)
- [GitHub releases](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/releases)

### Verifying GitHub Releases

See [VERIFYING_PGP_SIGNATURE](VERIFYING_PGP_SIGNATURE.md) for more information.

## Security

We take all security reports seriously. When we receive such reports, we will
investigate and subsequently address any potential vulnerabilities as quickly
as possible. If you discover a potential security issue in this project, please
notify AWS/Amazon Security via our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/)
or directly via email to [AWS Security](aws-security@amazon.com). Please do not
create a public GitHub issue in this project.

## License

This project is licensed under the Apache-2.0 License.
