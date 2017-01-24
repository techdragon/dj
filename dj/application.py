from __future__ import absolute_import

import os

from .addon import Addon
from .generator import Generator
from .blueprint import Blueprint
from .dependency import DependencyManager, Dependency
from .blueprint import get_core_blueprints
from .utils.system import (
    get_directories,
    get_last_touched,
    touch,
)
from .utils import style
from .config import Config
from .runtime import Runtime
from .utils.system import stdout as _stdout
from redbaron import RedBaron


class Application(object):

    def __init__(
        self,
        stdout=None,
        directory=None
    ):
        self.stdout = stdout or _stdout
        self.directory = directory or os.getcwd()
        self.config = Config(self.directory)

        self.setup_file = 'setup.py'
        self.requirements = self.config.get('requirements')
        self.dev_requirements = self.config.get('devRequirements')
        runtime = self.config.get('runtime')
        self.runtime = Runtime(runtime)

    def __unicode__(self):
        return '%s (%s)' % (self.name, self.directory)

    @staticmethod
    def parse_application_name(setup_filename):
        """Parse a setup.py file for the name.

        Returns:
            name, or None
        """
        with open(setup_filename, 'rt') as setup_file:
            fst = RedBaron(setup_file.read())
            for node in fst:
                if (
                    node.type == 'atomtrailers' and
                    str(node.name) == 'setup'
                ):
                    for call in node.call:
                        if str(call.name) == 'name':
                            value = call.value
                            if hasattr(value, 'to_python'):
                                value = value.to_python()
                            name = str(value)
                            break
                    if name:
                        break
        return name

    def _get_name(self):
        name = None
        setup_file = os.path.join(self.directory, self.setup_file)
        if os.path.exists(setup_file):
            try:
                name = Application.parse_application_name(setup_file)
            except Exception as e:
                import traceback
                raise Exception(
                    'Failed to parse app setup file: %s\n%s' %
                    (str(e), traceback.format_exc())
                )
        return name

    @property
    def name(self):
        if not hasattr(self, '_name'):
            self._name = self._get_name()
        return self._name

    @property
    def application_directory(self):
        return os.path.join(
            self.directory,
            self.name
        )

    @property
    def addons(self):
        if not hasattr(self, '_addons'):
            self._addons = {
                a.name: a for a in self.get_addons()
            }
        return self._addons

    def get_addons(self):
        self.build()

        addons = []
        for directory in get_directories(
            self.environment.package_directory,
            filter=lambda x: x.endswith('/blueprints')
        ):
            parent_directory = '/'.join(directory.split('/')[0:-1])
            name = os.path.basename(parent_directory)
            addons.append(Addon(name, parent_directory))
        return addons

    @property
    def blueprints(self):
        if not hasattr(self, '_blueprints'):
            self._blueprints = {
                ('%s.%s' % (b.addon.name, b.name) if b.addon else b.name): b
                for b in self.get_blueprints()
            }
        return self._blueprints

    def get_blueprints(self):
        addons = self.addons.values()
        blueprints = [a.blueprints.values() for a in addons]
        return [x for s in blueprints for x in s] + get_core_blueprints()

    @property
    def requirements_last_modified(self):
        return get_last_touched(
            os.path.join(self.directory, self.requirements)
        )

    @property
    def dev_requirements_last_modified(self):
        return get_last_touched(
            os.path.join(self.directory, self.dev_requirements)
        )

    @property
    def setup_last_modified(self):
        # timestamp of last setup.py change
        return get_last_touched(self.setup_file)

    @property
    def environment(self):
        if not hasattr(self, '_environment'):
            self._environment = self.runtime.create_environment(
                self.config.environment_path
            )
        return self._environment

    def _get_build_token(self, key):
        return os.path.join(
            self.environment.virtual_directory, 'build.%s' % key
        )

    def _build(self, key, last_modified, cmd, verbose=True):
        token = self._get_build_token(key)
        last_built = get_last_touched(token)
        if not last_built or last_built < last_modified:
            self.stdout.write(style.format_command('Building', key))
            result = self.execute(cmd, verbose=False, capture=True)
            if 'pip' in cmd:
                deps = []
                for line in result.split('\n'):
                    splits = line.split(' ')
                    if line.startswith('Successfully installed'):
                        dep = splits[2]
                        dep = '=='.join(dep.rsplit('-', 1))
                        dep = Dependency(dep)
                        deps.append((dep, style.green('+ ')))
                    elif line.startswith('Requirement already satisfied: '):
                        dep = splits[3]
                        dep = Dependency(dep)
                        deps.append((dep, style.yellow('. ')))
                    elif 'Uninstalling' in line:
                        index = line.index('Uninstalling')
                        dep = line[index:].split(' ')[1]
                        dep = ''.join(dep[0:len(dep) - 1])
                        dep = '=='.join(dep.rsplit('-', 1))
                        dep = Dependency(dep)
                        deps.append((dep, style.red('- ')))

                for dep, prefix in sorted(
                    deps,
                    key=lambda x: str(x[0])
                ):
                    self.stdout.write(prefix + dep.to_stdout())
            touch(token)

    def build(self):
        """Builds the app in the app's environment.

        Only builds if the build is out-of-date and is non-empty.
        Builds in 3 stages: requirements, dev requirements, and app.
        pip is used to install requirements, and setup.py is used to
        install the app itself.

        Raises:
            ValidationError if the app fails to build.
        """

        if self.name:
            self._build(
                'requirements',
                self.requirements_last_modified,
                'pip install -U -r %s' % self.requirements
            )
            self._build(
                'dev requirements',
                self.dev_requirements_last_modified,
                'pip install -U -r %s' % self.dev_requirements
            )
            self._build(
                'application',
                self.setup_last_modified,
                'python setup.py develop'
            )

    def execute(self, command, **kwargs):
        self.stdout.write(style.format_command('Running', command))
        return self.environment.execute(command, **kwargs)

    def run(self, command, **kwargs):
        self.build()
        return self.execute(command, **kwargs)

    def generate(self, blueprint, context):
        """Generate a blueprint within this application."""
        if not isinstance(blueprint, Blueprint):
            bp = self.blueprints.get(blueprint)
            if not bp:
                raise ValueError('%s is not a valid blueprint' % blueprint)
            blueprint = bp

        self.stdout.write(
            style.format_command(
                'Generating',
                blueprint.full_name
            )
        )
        generator = Generator(self, blueprint, context)
        result = generator.generate()
        if blueprint.name == 'init':
            # try re-setting the name
            self._name = self._get_name()
        return result

    def get_dependency_manager(self, dev=False):
        return DependencyManager(
            os.path.join(
                self.directory,
                self.dev_requirements if dev else self.requirements
            )
        )

    def add(self, addon, dev=False):
        """Add a new dependency and install it."""
        dependencies = self.get_dependency_manager(dev=dev)
        other_dependencies = self.get_dependency_manager(dev=not dev)
        existing = dependencies.get(addon)
        self.stdout.write(style.format_command('Adding', addon))
        dependencies.add(addon)
        try:
            # try adding
            self.build()
        except:
            # restore original settings
            dependencies.remove(addon)
            if existing:
                dependencies.add(existing)
            return

        # remove version of this in other requirements file
        other_dependencies.remove(addon, warn=False)

    def remove(self, addon, dev=False):
        """Remove a dependency and uninstall it."""
        dependencies = self.get_dependency_manager(dev=dev)
        other_dependencies = self.get_dependency_manager(dev=not dev)
        self.stdout.write(style.format_command('Removing', addon))
        removed = dependencies.remove(addon, warn=False)
        if not removed:
            removed = other_dependencies.remove(addon, warn=False)

        if removed:
            self.build()
        else:
            exception = '%s is not installed.' % Dependency(addon).to_stdout()
            self.stdout.write(style.red(exception))

    def info(self):
        output = []
        dev_requirements = self.get_dependency_manager(dev=True).dependencies
        requirements = self.get_dependency_manager(dev=False).dependencies
        name = self.name
        app = self.to_stdout()
        if name:
            output.append(style.blue('Application:\n %s' % app))
            if requirements:
                output.append(style.blue('Requirements:'))
                for _, dep in sorted(
                        requirements.items(),
                        key=lambda x: x[0].lower()):
                    output.append(' ' + dep.to_stdout())
            if dev_requirements:
                output.append(style.blue('Dev requirements:'))
                for _, dep in sorted(
                        dev_requirements.items(),
                        key=lambda x: x[0].lower()
                ):
                    output.append(' ' + dep.to_stdout())
        else:
            output.append(
                style.yellow(
                    '%s, try running %s.' % (
                        app, style.white('django init')
                    )
                )
            )

        return '\n'.join(output)

    def to_stdout(self):
        return '%s %s %s' % (
            style.white(self.name),
            style.gray('@'),
            style.green(self.runtime.version)
        ) if self.name else style.yellow('No application')

# singleton application instance
current_application = None


def get_current_application():
    global current_application
    if not current_application:
        current_application = Application()
    return current_application
