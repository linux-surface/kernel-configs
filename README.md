# Linux-surface Kernel Configurations

_Note:_
_These configurations will not be updated any more._
_Please use the fragments at [github.com/linux-surface/linux-surface][linux-surface-repo], the config provided by your distribution, and the `merge_config.sh` script provided by the kernel._

Kernel configurations for the linux-surface [kernel][linux-surface-kernel] and [patchset][linux-surface-repo].

## Configuration Files

A minimal list of Surface-specific configuration options is provided in `<version>/surface.config`.
You can combine this list with the base configuration provided by your distribution by use of the provided `genconf.py` script.
This script will warn you if it encounters any options that have unmet dependencies, so that you can fix these. See below for more information.

In addition, we provide some pre-generated and (somewhat) tested configs in `<version>/generated/<dist>-surface-<version>-<arch>.config`.
These are directly based on the base configuration `<version>/base/<dist>-<version>-<arch>.config`, which has been obtained from the respective distribution itself, e.g. from `https://kernel.ubuntu.com/~kernel-ppa/mainline/` for Ubuntu and via the Arch Build System for Arch Linux.

## Generating Configuration Files

Full configuration files can be generated via the `genconf.py` script provided in this repo.
As the dependencies are managed via `pipenv`, you will need to activate the virtual env via `pipenv shell` before you can run the script.
With this script, you can then merge multiple configuration files, e.g. the base configuration of your distribution and the `surface.conf` file for your desired kernel version via
```
./genconf.py <path-to-kernel-source-directory> <config-files>... -o <output-file>
```

Please pay attention to the warnings emmited by this scripts.
Most of them can be safely ignored, but you should ensure that all dependencies for the Surface related options are met.
To fix unmet dependencies, you can try running the script with the `-f` flag.
Note, however, that this may not produce the best results or may fail completely.

[linux-surface-repo]: https://github.com/linux-surface/linux-surface
[linux-surface-kernel]: https://github.com/linux-surface/kernel
