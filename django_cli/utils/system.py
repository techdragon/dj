import os
import sys
import subprocess


def get(
    directory,
    filter=None,
    depth=0,
    include_files=False,
    include_dirs=False
):
    if isinstance(filter, basestring):
        flt = lambda x: x == filter
    if not callable(filter):
        # if filter is None/unsupported type, allow all
        flt = lambda x: True
    else:
        flt = filter

    for root, dirs, files in os.walk(directory):
        search = []
        if include_files:
            search.extend(files)
        if include_dirs:
            search.extend(dirs)

        for file in search:
            file = os.path.join(root, file)
            if flt(file):
                yield file

        depth -= 1
        if depth == 0:
            break


def get_files(directory, filter=None, depth=0):
    return get(directory, filter, depth, include_files=True)


def get_directories(directory, filter=None, depth=0):
    return get(directory, filter, depth, include_dirs=True)


def get_last_touched(file):
    return os.path.getmtime(file) if os.path.exists(file) else None


def touch(file):
    with open(file, 'a'):
        os.utime(file, None)


def execute(
    command,
    abort=True,
    capture=False,
    verbose=False,
    echo=False,
    stream=None,
):
    """Run a command locally.

    Arguments:
        command: a command to execute.
        abort: If True, a non-zero return code will trigger an exception.
        capture: If True, returns the output of the command.
            If False, returns a subprocess result.
        echo: if True, prints the command before executing it.
        verbose: If True, prints the output of the command.
        stream: If set, stdout/stderr will be redirected to the given stream.
            Ignored if `capture` is True.
    """
    stream = stream or sys.stdout

    if echo:
        out = stream
        out.write(u'$ %s' % command)

    # Capture stdout and stderr in the same stream
    command = u'%s 2>&1' % command

    # Pipe output back into the main thread
    out = subprocess.PIPE
    err = subprocess.PIPE
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=out,
        stderr=err
    )

    if verbose:
        # Stream the results of the command into the given writer
        for line in iter(process.stdout.readline, ''):
            stream.write(line)

    # Wait for the process to complete
    stdout, _ = process.communicate()
    stdout = stdout.strip() if stdout else ''
    if not isinstance(stdout, unicode):
        stdout = stdout.decode('utf-8')

    if abort and process.returncode != 0:
        message = (
            u'Error (%d) running "%s":\n'
            '====================\n'
            '%s\n'
            '====================\n' % (
                process.returncode,
                command,
                stdout
            )
        )
        raise Exception(message)
    if capture:
        return stdout
    else:
        return process