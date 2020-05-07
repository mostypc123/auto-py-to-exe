from __future__ import print_function

import argparse
import io
import logging
import os
import shlex
import shutil
import sys
import traceback

from . import config
from . import __version__ as version

from PyInstaller.__main__ import run as run_pyinstaller


def __get_pyinstaller_argument_parser():
    from PyInstaller.building.makespec import __add_options as add_makespec_options
    from PyInstaller.building.build_main import __add_options as add_build_options
    from PyInstaller.log import __add_options as add_log_options

    parser = argparse.ArgumentParser()

    add_makespec_options(parser)
    add_build_options(parser)
    add_log_options(parser)

    parser.add_argument(
        'filenames', metavar='scriptname', nargs='+',
        help=("name of scriptfiles to be processed or "
              "exactly one .spec-file. If a .spec-file is "
              "specified, most options are unnecessary "
              "and are ignored.")
    )  # From PyInstaller.__main__.run

    return parser


def get_pyinstaller_options():
    parser = __get_pyinstaller_argument_parser()

    options = []
    for action in parser._actions:
        # Clean out what we can't send over to the ui
        # Here is what we currently have: https://github.com/python/cpython/blob/master/Lib/argparse.py#L771
        del action.container
        options.append(action)

    return [o.__dict__ for o in options]


def will_packaging_overwrite_existing(file_path, one_file, output_folder):
    """ Checks if there is a possibility of a previous output being overwritten. """
    if not os.path.exists(output_folder):
        return False
    no_extension = '.'.join(os.path.basename(file_path).split('.')[:-1])
    if one_file:
        if no_extension + '.exe' in os.listdir(output_folder):
            return True
    else:
        if no_extension in os.listdir(output_folder):
            return True
    return False


def __move_package(src, dst):
    """ Move the output package to the desired path (default is output/ - set in script.js) """
    # Make sure the destination exists
    if not os.path.exists(dst):
        os.makedirs(dst)

    # Move all files/folders in dist/
    for file_or_folder in os.listdir(src):
        _dst = os.path.join(dst, file_or_folder)
        # If this already exists in the destination, delete it
        if os.path.exists(_dst):
            if os.path.isfile(_dst):
                os.remove(_dst)
            else:
                shutil.rmtree(_dst)
        # Move file
        shutil.move(os.path.join(src, file_or_folder), dst)


class ForwardToFunctionStream(io.TextIOBase):
    def __init__(self, output_function=print):
        self.output_function = output_function

    def write(self, string):
        self.output_function(string)
        return len(string)


def setup_pyinstaller_logging(output_function=print):
    """ Link PyInstallers logging to the ui """
    logger = logging.getLogger('PyInstaller')
    handler = logging.StreamHandler(ForwardToFunctionStream(output_function))
    handler.setFormatter(logging.Formatter('%(relativeCreated)d %(levelname)s: %(message)s'))
    logger.addHandler(handler)


def package(pyinstaller_command, options, output_function=print):
    """
    Call PyInstaller to package a script using provided arguments and options.
    All output is passed to functions provided.
    :param pyinstaller_command: Command to supply to PyInstaller
    :param options: auto-py-to-exe specific options for setup and cleaning up
    :param output_function: A function to output messages to e.g. output_function("Output Message")
    :return: Whether packaging was successful
    """

    # Show current version
    output_function("Running auto-py-to-exe v" + version)

    # Notify the user of the workspace and setup building to it
    output_function("Building directory: {}\n".format(config.temporary_directory))

    # Override arguments
    dist_path = os.path.join(config.temporary_directory, 'application')
    build_path = os.path.join(config.temporary_directory, 'build')
    extra_args = ['--distpath', dist_path] + ['--workpath', build_path] + ['--specpath', config.temporary_directory]

    output_function('Provided command: {}\n'.format(pyinstaller_command))

    # Setup options
    increase_recursion_limit = options['increaseRecursionLimit']
    output_directory = os.path.abspath(options['outputDirectory'])

    if increase_recursion_limit:
        sys.setrecursionlimit(5000)
        output_function("Recursion Limit is set to 5000\n")
    else:
        sys.setrecursionlimit(config.DEFAULT_RECURSION_LIMIT)

    # Run PyInstaller
    fail = False
    try:
        # Since we allow manual argument input, we cannot pass arguments to PyInstaller as a list as we can't
        # guarantee that the arguments will be parsed correctly. To get around this, we can set sys.argv here with our
        # command to trick PyInstaller to reading the command as if we are using the cli tool.
        sys.argv = shlex.split(pyinstaller_command) + extra_args  # Put command into sys.argv and extra args

        # Display the command we are using and leave a space to separate out PyInstallers logs
        output_function('Executing: {}\n'.format(' '.join(sys.argv)))
        output_function('\n')

        run_pyinstaller()
    except:
        fail = True
        output_function("An error occurred, traceback follows:\n")
        output_function(traceback.format_exc())

    # Move project if there was no failure
    output_function("\n")
    if not fail:
        output_function("Moving project to: {0}\n".format(output_directory))
        try:
            __move_package(dist_path, output_directory)
        except:
            output_function("Failed to move project, traceback follows:\n")
            output_function(traceback.format_exc())
    else:
        output_function("Project output will not be moved to output folder\n")
        return False

    # Set complete
    return True