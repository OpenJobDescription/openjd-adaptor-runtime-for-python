# PROPOSAL: Worked Example of a Blender Adaptor

## Table of Contents

- [Introduction](#introduction)
- [Batch Workloads in Blender](#batch-workloads-in-blender)
  - [Rendering](#rendering)
  - [Custom Scripting](#custom-scripting)
- [Evaluate Open Job Description application interface patterns](#evaluate-open-job-description-application-interface-patterns)
  - [Run as a background daemon](#run-as-a-background-daemon)
  - [Report progress and status messages](#report-progress-and-status-messages)
  - [Map file system paths](#map-file-system-paths)
  - [Task chunking](#task-chunking)
- [Designing the Blender adaptor CLI interface](#designing-the-blender-adaptor-cli-interface)
  - [Requirements for the adaptor user experience](#requirements-for-the-adaptor-user-experience)
  - [Adaptor CLI interface design](#adaptor-cli-interface-design)
  - [Map file system paths](#map-file-system-paths-1)
  - [Render task chunks](#render-task-chunks)

## Introduction

This document provides a worked example of the thought process behind designing a new interface for
the Blender Open Job Description adaptor, implemented in
[deadline-cloud-for-blender](https://github.com/aws-deadline/deadline-cloud-for-blender).
The current adaptor interface is significantly different from how users run Blender batch
workloads today, and I believe we can do better.

The goal is to build an application interface for Blender that simplifies Open Job Description job templates for Blender workloads.
This means the adaptor should be intuitive for someone already familiar with running workloads in Blender, but also have
simple ways to support the features listed in the [project README](../README.md).

Therefore, before we can define this adaptor, we must understand Blender's existing support
for batch workloads. Then we can identify what benefits an adaptor would provide over just
using Blender's existing support, and finally design the application interface it should
provide.

If this is successful, we propose to extend this same thought process to all the other `deadline-cloud-for-<dcc>`
projects, and modify the [job_env_daemon_process](https://github.com/aws-deadline/deadline-cloud-samples/blob/mainline/job_bundles/job_env_daemon_process/template.yaml)
sample job template to demonstrate this library as well.

## Batch Workloads in Blender

Our first step is to understand the batch workloads users want to run in Blender.
The Blender documentation topic [Using Blender From The Command Line](https://docs.blender.org/manual/en/latest/advanced/command_line/index.html)
describes two cases: [rendering animation](https://docs.blender.org/manual/en/latest/advanced/command_line/render.html#command-line-render),
and launching Blender with [different arguments](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html#command-line-args).

### Rendering

Two options, `-f` (`--render-frame`) and `-a` (`--render-anim`), cause it to render frames and save the images.
Here's an example rendering command you could include in a job template:

```sh
blender --background '{{Param.BlenderSceneFile}}' \
        --render-output '{{Param.OutputDir}}/{{Param.OutputPattern}}' \
        --render-format {{Param.Format}} \
        --use-extension 1 \
        --render-frame {{Task.Param.Frame}}
```

### Custom Scripting

The options `-P` (`--python`), `--python-text`, and `--python-expr` cause it to run Python code.
Here's an example custom workload command using the Blender Python API for file conversion:

```sh
blender --factory-startup \
        --background \
        --python-exit-code 1 \
        --python-use-system-env \
        --python scripts/blender_file_conversion.py \
        -- \
        --input {{Param.InputFile}} \
        --output {{Param.OutputFile}}
```

Inside `blender_file_conversion.py` you might find the following argument processing:

```python
import argparse
...

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    run_file_conversion(args.input, args.output)

if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
```

## Evaluate Open Job Description application interface patterns

With an idea of the batch workloads to run on Blender, let's look at how they fit into
Open Job Description job templates expressing various workload patterns.

### Run as a background daemon

For this pattern, Blender should stay open in the background, then the job runs commands
in sequence to render individual frames or run custom scripts in that persistent Blender
process. The Deadline Cloud samples github repository has an example job template,
[Job Environment Daemon Process](https://github.com/aws-deadline/deadline-cloud-samples/blob/mainline/job_bundles/job_env_daemon_process/template.yaml)
to illustrate the pattern where a step environment called DaemonProcess loads a process in
the background for the tasks of the step EnvWithDaemonProcess.

The [Blender CLI command](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html)
has a `--background` option, but this option means to not show a GUI, not to load a
persistent background daemon and then send commands to it.

As there is no built-in background daemon support in Blender, but Blender provides
flexible Python scripting, we can add support for it in an adaptor.

### Report progress and status messages

While rendering, Blender prints output that look like this:

```sh
$ blender --background '/.../blender-3.5-splash.blend' \
          --render-output '/.../output_####' \
          --render-format JPEG \
          --use-extension 1 \
          --render-frame 1
Blender 4.4.0 (hash 05377985c527 built 2025-03-18 03:01:40)
Read blend: "/.../blender-3.5-splash.blend"
Fra:1 Mem:421.62M (Peak 422.43M) | Time:00:12.91 | Mem:0.00M, Peak:0.00M | Main, ViewLayer | Synchronizing object | Icosphere
...
Fra:1 Mem:564.29M (Peak 663.39M) | Time:00:15.28 | Mem:337.70M, Peak:340.61M | Main, ViewLayer | Loading denoising kernels (may take a few minutes the first time)
Fra:1 Mem:564.29M (Peak 663.39M) | Time:00:15.28 | Mem:337.70M, Peak:340.61M | Main, ViewLayer | Sample 0/128
Fra:1 Mem:684.53M (Peak 684.53M) | Time:00:23.55 | Remaining:17:31.44 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Sample 1/128
...
Fra:1 Mem:735.16M (Peak 811.09M) | Time:17:27.41 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Sample 128/128
Fra:1 Mem:735.16M (Peak 811.09M) | Time:17:27.41 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Finished
Fra:1 Mem:292.20M (Peak 811.09M) | Time:17:27.44 | Compositing
Saved: '/.../output_0001.jpg'
Time: 17:27.67 (Saving: 00:00.17)
```

Per the [Open Job Description stdout/stderr messages documentation](https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#stdoutstderr-messages),
Blender could print message like the following to report completion progress and status messages, that the queuing
system will know to report back to the user in their dashboard view:

```
openjd_progress: 32%
openjd_status: Loading denoising kernels (may take a few minutes the first time)
```

As Blender does not have an option to print messages in this format, we can add support in an adaptor, by reading
the output from Blender and printing lines in the Open Job Description format.

### Map file system paths

When a queuing system runs jobs on a different operating system, or with files located at different paths,
the job needs to transform any absolute path references in the input data for processing to work.
Open Job Description provides [Path Mapping rules](https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#path-mapping)
that a job template can use to learn about which paths to map.

Blender has options to control use of [Relative vs Absolute Paths](https://docs.blender.org/manual/en/latest/files/blend/open_save.html#files-blend-relative-paths),
and defaults to using relative paths when possible. If a Blender scene uses only relative paths, no
custom path mapping will be necessary, because the system will handle re-mapping the scene file path
as a job parameter with type PATH, and all the other paths will be relative to that. Users can choose
to use absolute paths, or on Windows they can use multiple drive letters, in which case there is no
way to make all paths relative. In those cases, the job template will need to handle path mapping.

As Blender does not have a built-in path mapping mechanism based on the Open Job Description path
mapping rule format, this is something for the adaptor to handle.

### Task chunking

Open Job Description [RFC 0001](https://github.com/OpenJobDescription/openjd-specifications/blob/mainline/rfcs/0001-task-chunking.md)
introduced a mechanism to run multiple tasks in a single action as a chunk. When running a chunk, the frame
numbers are provided as an [Open Job Description integer range expression](https://github.com/OpenJobDescription/openjd-specifications/wiki/2023-09-Template-Schemas#34111-intrangeexpr).
The Blender `--render-frame` CLI option supports a syntax that is similar, but different from this syntax.
An adaptor can accept the Open Job Description syntax and transform it for Blender.

## Designing the Blender adaptor CLI interface

### Requirements for the adaptor user experience

The best user experience would be for users to directly use the Blender CLI in Open Job Description
job templates, and for it to be simple and straightforward. This leads us to our first goal of the
CLI interface we will design:

* The adaptor CLI interface should be as close to the existing Blender CLI as we can make it, with
  the following properties:
    * If an existing Blender CLI option is useful for batch processing, the adaptor should support it exactly.
    * If the adaptor includes a CLI option that is not part of the Blender CLI, try to make it fit
      in to the Blender CLI commands as naturally as possible. To evaluate an addition, imagine pitching to
      the Blender Foundation that they should add the command to Blender directly, and consider how convincing
      your case is.

Because the adaptor will be a separate command from Blender like `blender-openjd` instead of `blender`,
authors of job templates should be able to easily take a CLI `blender` command, switch it to `blender-openjd`,
and make minimal changes to use the Open Job Description features. Similarly, taking a `blender-openjd` command
and adjusting it to be a straight `blender` command should also be easy.

* Any adaptor CLI options that are not in the `blender` CLI should be easily identifiable.
    * If the feature is specific to Open Job Description, likely include `openjd` in the option name somewhere.
    * If the feature could be added to the `blender` CLI directly without any Open Job Description
      reference, and would make sense, craft a clear rationale for the choice.

With the desire to keep the possibility of Blender itself implementing the CLI options of the adaptor CLI,
the behavior of the adaptor needs to be compatible. That leads to:

* When calling the adaptor CLI with options also available in the Blender CLI, the behavior such as the
  output it prints should be as identical to Blender as possible.

### Adaptor CLI interface design

#### Start a background Blender daemon

Starting a daemon returns an address necessary to access it later, that can be stored in an environment
variable. This address is used by the run and stop daemon operations. Most workloads will start only one
Blender daemon, and we will provide a simple way to express this in a job template without boilerplate.
Some workloads will start multiple Blender daemons, and they must track multiple daemon addresses.

We will add two CLI options for starting a background Blender daemon. The `--background` cannot be used together with
these options, but it is automatically enabled when they are used. Additional options provided in the command are the same as for the
`blender` command, and are directives for how to initialize Blender once it has loaded, such as to open a `.blend` scene file,
apply path mapping rules, or modify the output image resolution.

```sh
# Start a Blender background daemon and print 'openjd_env: BLENDER_DAEMON_ADDRESS=<implementation-defined-address>'
# for Open Job Description to use.
$ blender-openjd --openjd-daemon-start ...
openjd_env: BLENDER_DAEMON_ADDRESS=<implementation-defined-address>

# Start a Blender background daemon and print '<implementation-defined-address>'. Can be used from any shell
# scripting context like 'export BLENDER_DAEMON_ADDRESS=$(blender-openjd --daemon-start ...)'
$ blender-openjd --daemon-start ...
<implementation-defined-address>
```

Here is example usage within a job template
[onEnter](https://github.com/OpenJobDescription/openjd-specifications/wiki/2023-09-Template-Schemas#43-environmentactions)
action.

```yaml
...
  actions:
    onEnter:
      # This form lets you directly start the daemon without manipulating any variables
      command: blender-openjd
      args: ["--openjd-daemon-start", "{{Param.BlenderFile}}"]
```

```yaml
...
  actions:
    onEnter:
      command: "bash"
      args: ["{{Env.File.OnEnter}}"]
  embeddedFiles:
  - name: OnEnter
    filename: on-enter.sh
    type: TEXT
    data: |
      set -euo pipefail

      # This matches the default behavior of the --openjd-daemon-start option
      export BLENDER_DAEMON_ADDRESS="$(blender-openjd --daemon-start {{Param.BlenderFile}})"
      echo "openjd_env: BLENDER_DAEMON_ADDRESS=$BLENDER_DAEMON_ADDRESS"

      # You can use this form to start multiple independent Blender background daemons.
      export BLENDER_DAEMON_ADDRESS_2="$(blender-openjd --daemon-start {{Param.BlenderFile}})"
      echo "openjd_env: BLENDER_DAEMON_ADDRESS_2=$BLENDER_DAEMON_ADDRESS_2"
```

#### Run commands in the daemon

Just like for starting a daemon, we will provide two options to run commands in the daemon. Each
command is equivalent to `blender --background ...`, but runs within the background daemon instead
of in a new Blender process.

```sh
# Run commands in the daemon at address $BLENDER_DAEMON_ADDRESS
$ blender-openjd --openjd-daemon-run ...

# Run commands in the specified address
$ blender-openjd --daemon-run <implementation-defined-address> ...
```

Here is example usage within a job template
[onRun](https://github.com/OpenJobDescription/openjd-specifications/wiki/2023-09-Template-Schemas#351-stepactions)
action.

```yaml
...
  actions:
    onRun:
      # This form lets you directly run commands in the daemon without manipulating any variables
      command: blender-openjd
      args: ["--openjd-daemon-run", "--render-frame", "{{Task.Param.Frame}}"]
```

```yaml
...
  actions:
    onRun:
      command: "bash"
      args: ["{{Env.File.OnRun}}"]
  embeddedFiles:
  - name: OnRun
    filename: on-run.sh
    type: TEXT
    data: |
      set -euo pipefail

      # This matches the default behavior of the --openjd-daemon-run option
      blender-openjd --daemon-run "$BLENDER_DAEMON_ADDRESS" --render-frame "{{Task.Param.Frame}}"

      # You can use this form to run commands in multiple independent Blender background daemons.
      blender-openjd --daemon-run "$BLENDER_DAEMON_ADDRESS_2" --render-frame "{{Task.Param.Frame}}"
```

#### Stop the daemon

We provide two options to stop the daemon. One that uses the default environment variable name, and
a second that accepts the daemon address as an option.

```sh
# Stop the daemon at address $BLENDER_DAEMON_ADDRESS
$ blender-openjd --openjd-daemon-stop

# Stop the daemon at the specified address
$ blender-openjd --daemon-stop <implementation-defined-address>
```

Usage within a job template is straightforward.

```yaml
...
  actions:
    onEnter:
      command: blender-openjd
      args: ["--openjd-daemon-stop"]
```

```yaml
...
  actions:
    OnExit:
      command: "bash"
      args: ["{{Env.File.OnExit}}"]
  embeddedFiles:
  - name: OnExit
    filename: on-exit.sh
    type: TEXT
    data: |
      set -euo pipefail

      # This matches the default behavior of the --openjd-daemon-stop option
      blender-openjd --daemon-stop "$BLENDER_DAEMON_ADDRESS"

      # You can use this form to stop other Blender daemons
      blender-openjd --daemon-stop "$BLENDER_DAEMON_ADDRESS_2"
```

#### Open Job Description progress and status messages

We will provide one option to enable progress and status messages, `--openjd-updates`. Typically this will
be used immediately after the `--background` or `--openjd-daemon-start` options, to provide Open Job Description
progress updates for the lifetime of the Python process being launched, whether it runs as a single command or
as a daemon.

When this option is enabled, rendering output will include `openjd_status` and `openjd_progress` messages. This
will not affect custom scripts, it is up to authors of those custom batch processing scripts to output
suitable status and progress messages.

An example of what that might look like:

```sh
$ blender-openjd --background '/.../blender-3.5-splash.blend' \
          --openjd-updates \
          --render-output '/.../output_####' \
          --render-format JPEG \
          --use-extension 1 \
          --render-frame 1
Blender 4.4.0 (hash 05377985c527 built 2025-03-18 03:01:40)
openjd_status: Read blend: "/.../blender-3.5-splash.blend"
openjd_status: Preparing frame 1...
Fra:1 Mem:421.62M (Peak 422.43M) | Time:00:12.91 | Mem:0.00M, Peak:0.00M | Main, ViewLayer | Synchronizing object | Icosphere
...
Fra:1 Mem:564.29M (Peak 663.39M) | Time:00:15.28 | Mem:337.70M, Peak:340.61M | Main, ViewLayer | Loading denoising kernels (may take a few minutes the first time)
Fra:1 Mem:564.29M (Peak 663.39M) | Time:00:15.28 | Mem:337.70M, Peak:340.61M | Main, ViewLayer | Sample 0/128
openjd_status: Rendering frame 1...
Fra:1 Mem:684.53M (Peak 684.53M) | Time:00:23.55 | Remaining:17:31.44 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Sample 1/128
openjd_progress: 1
...
Fra:1 Mem:684.53M (Peak 684.53M) | Time:07:41.36 | Remaining:10:35.98 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Sample 49/128
openjd_progress: 38
...
Fra:1 Mem:684.53M (Peak 684.53M) | Time:13:13.38 | Remaining:04:02.92 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Sample 96/128
openjd_progress: 75
...
Fra:1 Mem:735.16M (Peak 811.09M) | Time:17:27.41 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Sample 128/128
openjd_progress: 100
Fra:1 Mem:735.16M (Peak 811.09M) | Time:17:27.41 | Mem:457.94M, Peak:457.94M | Main, ViewLayer | Finished
Fra:1 Mem:292.20M (Peak 811.09M) | Time:17:27.44 | Compositing
openjd_status: Saved: '/.../output_0001.jpg'
Time: 17:27.67 (Saving: 00:00.17)
```

### Map file system paths

We will provide an option `--openjd-path-mapping-rules <path-mapping-file>` to load path mapping metadata in
[the format specified by Open Job Description](https://github.com/OpenJobDescription/openjd-specifications/wiki/How-Jobs-Are-Run#path-mapping).
This metadata will apply to any later scene file loading operations, so it should be specified earlier than any `.blend` files provided
as part of the command. Typically this will be used immediately after the `--background` or `--openjd-daemon-start` options, or right
before the first `.blend` file specified at the command line.

An example command in a job template may look like the following, with a template value substitution for the path mapping
rules that the job runtime gives it.

```sh
# PATH_MAPPING_RULES comes from {{Session.PathMappingRulesFile}} in a job template
$ blender-openjd --background \
          --openjd-path-mapping-rules "$PATH_MAPPING_RULES" \
          '/.../blender-3.5-splash.blend' \
          --render-output '/.../output_####' \
          --render-format JPEG \
          --use-extension 1 \
          --render-frame 1
```

### Render task chunks

We will provide an option `--openjd-render-frame` that is identical to `--render-frame` but accepts frame numbers in the
[Open Job Description range expression](https://github.com/OpenJobDescription/openjd-specifications/wiki/2023-09-Template-Schemas#34111-intrangeexpr)
format instead of the usual Blender format.

```sh
$ blender-openjd --background '/.../blender-3.5-splash.blend' \
          --render-output '/.../output_####' \
          --render-format JPEG \
          --use-extension 1 \
          --openjd-render-frame "1-5:2,9-11,15"
```

The equivalent command with `--render-frame` would be

```sh
$ blender --background '/.../blender-3.5-splash.blend' \
          --render-output '/.../output_####' \
          --render-format JPEG \
          --use-extension 1 \
          --render-frame "1,3,5,9..11,15"
```

## Implementation and release strategy

There is already a Blender adaptor with an interface different from this proposal. This adaptor is also the pilot
project to show a better way for all the adaptors to work, where we migrate the interfaces of each
`deadline-cloud-for-<dcc>` project to follow a pattern extending the DCC's CLI interface replacing the
YAML-based options.

Here's the current interface for `blender-openjd`:

```sh
$ blender-openjd -h
usage: BlenderAdaptor <command> [arguments]

options:
  -h, --help            show this help message and exit

commands:
  {show-config,version-info,is-compatible,run,daemon}
    show-config         Prints the adaptor runtime configuration, then the program exits.
    version-info        Prints CLI and data interface versions, then the program exits.
    is-compatible       Validates compatiblity for the adaptor CLI interface and integration data interface provided
    run                 Run through the start, run, stop, cleanup adaptor states.
    daemon              Runs the adaptor in a daemon mode.
```

Observe that none of the sub-commands overlap with the new proposed API, so we can make the command
provide both interfaces simultaneously. Our release strategy can therefore be a two-phase deployment:

1. First we implement and release the new interface into the existing CLI command. Previous usage
   of the adaptor remains unchanged, because it does not overlap with the new options.
2. Next we modify the submitter GUI that's integrated with Blender to support the new interface,
   and release it behind a feature flag.
3. After thorough testing and validation, we change the submitter GUI default to use the new interface.
4. Finally, we remove the code for the old interface.
