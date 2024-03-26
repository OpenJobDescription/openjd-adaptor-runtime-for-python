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

### Running an Adaptor
Adaptors can operate in two modes: Foreground and Background. In the below section, we will use the `AdaptorExample` 
to show how they work. Following commands need to be run in the `test\openjd\adaptor_runtime\`. Please navigate to 
this directory by using the `cd`. 

#### Foreground Mode
In Foreground Mode, the adaptor undergoes a complete lifecycle including `start`, `run`, `stop` and `cleanup` of the 
adaptor in a single command.
This mode is straightforward and is recommended for linear task execution.  Additionally, the Foreground Mode supports 
the injection of initialization and runtime data through the `--init-data` and `--run-data` flags. 
These flags allow for the passing of a JSON-encoded dictionary, either directly in the command line or through a file. 
- **`--init-data`**: This data is decoded and stored within the `self.init_data` attribute.
- **`--run-data`**: This data becomes accessible as the first argument of the `on_run` method.

```
python -m integ.AdaptorExample run --init-data '{"name": "MyAdaptor"}'  --run-data '{"hello": "world"}'
```

#### Background Mode
Background Mode is provided to enable scenarios where it is beneficial to maintain state between multiple runs.
Such as between task runs within an 
[Open Job Description Session](https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#sessions).
You can use it with any type of Adaptor, but it derives its greatest benefit with Adaptors derived from
the `Adaptor` class rather than the `CommandAdaptor` class.
An example of how you might design an Adaptor to leverage this mode is to have it:
1. Load an application in the Adaptor's `start` phase; then
2. Communicate with that loaded application in each `run` of the Adaptor to tell the application what to do; then
3. Close the application in the Adaptor's `stop` phase.
In this mode, your Adaptor is started up as a background process and left running. Then you can invoke
your Adaptor again to connect to that background process and instruct it to perform actions. When
connecting to the background process your command will relay all log output from the background process
to your stdout and stderr, and will only exit once the command is complete.

When using background mode, you have to manage the state transitions of the Adaptor yourself by repeatedly running the 
adaptor with different arguments.
1. Start the Adaptor: Initializes the adaptor and prepares it for background operation. This starts up your
   Adaptor in a subprocess that is left running after the command exits. You must provide a path to a
   connection file for the Adaptor to create. This file contains information on how to connect to the
   subprocess that is left running, and you must provide it to all subsequent runs of the Adaptor until you
   have stopped it. You may also provide `--init-data` to the start command that is a JSON-encoded
   dictionary either inline or in a given file; this data is decoded and automatically stored in the
   `self.init_data` member of your running Adaptor.
    ```
    python -m integ.AdaptorExample daemon start --connection-file ./AdaptorExampleConnection.json --init-data '{"name": "MyAdaptor"}'
    ```
2. Run the Adaptor: Executes the adaptor's main functionality. This step can be repeated multiple times, 
optionally passing custom data via the `--run-data` argument to modify the operation context.
This data becomes accessible as the first argument of the `on_run` method of your running Adaptor.
    ```
    python -m integ.AdaptorExample daemon run --connection-file ./AdaptorExampleConnection.json
    ```
    To pass custom data:
    ```
    python -m integ.AdaptorExample daemon run --connection-file ./AdaptorExampleConnection.json --run-data '{"hello": "world"}'
    ```
3. Stop the Adaptor: Terminates the adaptor's operation and performs necessary cleanup actions. 
This step ensures that the background processes are properly closed, and the IPC channel is cleaned up.
    ```
    python -m integ.AdaptorExample daemon stop --connection-file ./AdaptorExampleConnection.json
    ```

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.
