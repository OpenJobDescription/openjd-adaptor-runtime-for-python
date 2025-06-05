# Open Job Description Adaptor Runtime Library - Documentation

## Usage

To create your own Adaptor you create a Python application that uses this package and consists of:

1. A console script entrypoint that passes control flow to an instance of this runtime's **EntryPoint** class;
2. A JSON file for configuration options of your Adaptor; and
3. An Adaptor class derived from either the **CommandAdaptor** or **Adaptor** class.
    - **CommandAdaptor** is ideal for applications where you do not need to initialize the local compute environment by, say,
       preloading your application, and simply need to run a single commandline for each Task that is run on the compute host.
       Please see [CommandAdaptorExample] in this GitHub repository for a simple example.
    - **Adaptor** exposes callbacks for every stage of an Adaptor's lifecycle, and is is suited for Adaptors where you want full control.
       Please see [AdaptorExample] in this GitHub repository for a simple example.

You can also find many more examples within the [AWS Deadline Cloud Organization] on GitHub.

[CommandAdaptorExample]: https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/tree/release/test/openjd/adaptor_runtime/integ/CommandAdaptorExample
[AdaptorExample]: https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/tree/mainline/test/openjd/adaptor_runtime/integ/AdaptorExample
[AWS Deadline Cloud Organization]: https://github.com/aws-deadline

### Adaptor Lifecycle

All Adaptors undergo a lifecycle consisting of the following stages:

1. **start**: Occurs once during construction and initialization of the Adaptor. This is the stage where
   your Adaptor should perform any expensive initialization actions for the local compute environment; such
   as starting and loading an application in the background for use in later stages of the Adaptor's lifecycle.
    - Runs the `on_start()` method of Adaptors derived from the **Adaptor** base class.
2. **run**: May occur one or more times for a single running Adaptor. This is the stage where your Adaptor is
   performing the work required of a Task that is being run.
    - Run the `on_run()` method of Adaptors derived from the **Adaptor** base class.
    - Run the `on_prerun()` then `get_managed_process()` then `on_postrun()` methods of Adaptors derived from the
     **CommandAdaptor** base class.
3. **stop**: Occurs once as part of shutting down the Adaptor. This stage is the inverse of the **start**
   stage and should undo the actions done in that phase; such as stopping any background processes that are
   still running.
    - Runs the `on_stop()` method of Adaptors derived from the **Adaptor** base class.
4. **cleanup**: A final opportunity to cleanup any remaining processes and data left behind by the Adaptor.
    - Runs the `on_cleanup()` method of Adaptors derived from the **Adaptor** base class.

A running Adaptor can also be canceled by sending the Adaptor process a signal (SIGINT/SIGTERM on posix, or
CTRL-C/CTRL-BREAK on Windows). This will call the `on_cancel()` method of your Adaptor, if one is defined.
You should ensure that the design of your Adaptor allows this cancelation to interrupt any actions that may
be running, and gracefully exit any running background processes.

### Running an Adaptor

The **EntryPoint** provided by this runtime allows for an Adaptor to be run directly through its
entire lifecycle in a single command, or to be run as a background daemon that lets you drive the lifecycle
of the Adaptor yourself.

#### The `run` Subcommand

The `run` subcommand of an Adaptor will run it through its entire lifecycle (**start**, then **run**, then
**stop**, and finally **cleanup**), and then exit. This is useful for initial development and testing, and
for running Adaptors created from the **CommandAdaptor** base class.

To see this in action install the openjd-adaptor-runtime package into your Python environment, and then
within your local clone of this repository:

```bash
cd test/openjd
python3 -m integ.AdaptorExample run --init-data '{"name": "MyAdaptor"}'  --run-data '{"hello": "world"}'
```

The arguments to the `run` subcommand are:

- **`--init-data`** is a JSON-encoded dictionary either inline or in a given file (`file://<path-to-file>`). This data is
  decoded and automatically stored in the `self.init_data` member of the running Adaptor.
- **`--run-data`** is, similarly, a JSON-encoded dictionary either inline or in a given file (`file://<path-to-file>`).
  This data is passed as the argument to the `on_run()` method of an **Adaptor** or the `get_managed_process()`
  method of a **CommandAdaptor**.

#### The `daemon` Subcommand

With the `daemon` subcommand, you must transition the Adaptor through its lifecycle yourself by running the
subcommands of the `daemon` subcommand in order.

1. Start the Adaptor: Initializes the Adaptor as a background daemon subprocess and leaves it running.
   This runs the `on_start()` method of your **Adaptor**-derived Adaptor if the method is available.
    ```
    python -m integ.AdaptorExample daemon start --connection-file ./AdaptorExampleConnection.json --init-data '{"name": "MyAdaptor"}'
    ```
   - **`--init-data`** is as described in the `run` subcommand, above.
   - **`--connection-file`** provide a path to a JSON file for the Adaptor to create. This file contains information
     on how to connect to the daemon subprocess remains running, and you must provide it to all subsequent runs of the
     Adaptor until you have stopped it.
2. Run the Adaptor: Connects to the daemon subprocess that is running the Adaptor and instructs it to perform its **run**
   lifecycle phase. The command remains connected to the daemon subprocess for the entire duration of this **run** phase,
   and forwards all data logged by the Adaptor to stdout or stderr. This step can be repeated multiple times.
    ```
    python -m integ.AdaptorExample daemon run --connection-file ./AdaptorExampleConnection.json --run-data '{"hello": "world"}'
    ```
   - **`--run-data`** is as described in the `run` subcommand, above.
   - **`--connection-file`** is as described above.
3. Stop the Adaptor: Connects to the daemon subprocess that is running the Adaptor and instructs it to transition to the
   **stop** then **cleanup** lifecycle phases, and then instructs the daemon subprocess to exit when complete. The command
   remains connected to the daemon subprocess for the entire duration, and forwards all data logged by the Adaptor to stdout
   or stderr.
    ```
    python -m integ.AdaptorExample daemon stop --connection-file ./AdaptorExampleConnection.json
    ```
