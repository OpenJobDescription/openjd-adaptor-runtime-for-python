# Open Job Description - Adaptor Runtime

This package provides a runtime library that can be used to implement a CLI adaptor interface around
a desired application.

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

## Usage
This package offers two primary adaptor types: `CommandAdaptor` and `Adaptor`, designed for customization for various use cases. 
All adaptors can operate in two modes Foreground and Background to meet different requirements, 
Below is an overview of how these adaptors work.

### Adaptor Types

- **CommandAdaptor**: Ideal for executing straightforward commands. Extend this class if your requirements involve 
simple command execution. An implementation example is available at `test/openjd/adaptor_runtime/integ/CommandAdaptorExample`.

- **Adaptor**: Suited for applications that demand granular control, such as digital content creation (DCC) applications. 
By inheriting from `Adaptor`, you can predefine actions for reuse across different contexts. 
An example adaptor could be found at `test/openjd/adaptor_runtime/integ/AdaptorExample`.

### Adaptor Running Mode:
Adaptors can operate in two modes: Foreground and Background. In the below section, we will use the `AdaptorExample` 
to show how they work. Following commands need to be run in the `test\openjd\adaptor_runtime\`. Please navigate to 
this directory by using the `cd`. 

#### Foreground Mode
In Foreground Mode, the adaptor undergoes a complete lifecycle including `start`, `run`, `stop` and `cleanup` of the adaptor in a single command.
This mode is straightforward and is recommended for linear task execution.
```
python -m integ.AdaptorExample run
```

#### Background Mode
Background Mode is optimized for scenarios required maintaining an application's state across multiple operations. 
This mode enhances efficiency by reusing the application's loaded state.

1. Start the Adaptor: Initializes the adaptor and prepares it for background operation.
    ```
    python -m integ.AdaptorExample daemon start --connection-file ./AdaptorExampleConnection.json
    ```
1. Run the Adaptor: Executes the adaptor's main functionality. This step can be repeated multiple times, 
optionally passing custom data via the `--run-data` argument to modify the operation context.
    ```
    python -m integ.AdaptorExample daemon run --connection-file ./AdaptorExampleConnection.json
    ```
    To pass custom data:
    ```
    python -m integ.AdaptorExample daemon run --connection-file ./AdaptorExampleConnection.json --run-data '{"hello": "world"}'
    ```
1. Stop the Adaptor: Terminates the adaptor's operation and performs necessary cleanup actions. 
This step ensures that the background processes are properly closed, and the IPC channel is cleaned up.
    ```
    python -m integ.AdaptorExample daemon stop --connection-file ./AdaptorExampleConnection.json
    ```

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.
