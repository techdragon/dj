from collections import OrderedDict
import os
import re
from copy import copy
from dj.utils.system import stdout
from dj.utils.style import white, green, red, yellow, gray


class Dependency(object):
    parse_regex = re.compile(r'^([A-Za-z][-A-Za-z0-9_.]+)([=><]+)([0-9.]+)$')

    def __init__(self, value):
        value = value.strip('\n')
        self.value = value
        self.name, self.operator, self.version = Dependency.parse(value)

    @classmethod
    def parse(cls, value):
        result = cls.parse_regex.match(value)
        if result:
            name = result.group(1)
            operator = result.group(2)
            version = result.group(3)
        else:
            name = value
            operator = ''
            version = ''
        return name, operator, version

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return '%s%s%s' % (self.name, self.operator, self.version)

    def to_stdout(self):
        return '%s %s %s' % (
            white(self.name),
            gray(self.operator),
            green(self.version)
        ) if self.operator else white(self.name)


class DependencyManager(object):

    def __init__(self, source):
        self.source = source

    def add(self, value, warn=True):
        new = Dependency(value)
        new_label = new.to_stdout()
        old = self.dependencies.get(new.name)
        self.dependencies[new.name] = new
        if old is None or str(old) != str(new):
            old_label = old.to_stdout() if old else ''

            self._save()
            if old_label:
                stdout.write(red('- ') + old_label)
            stdout.write(green('+ ') + new_label)
            return True
        else:
            if warn:
                stdout.write(
                    '%s %s' %
                    (new_label, yellow('already installed.')))
            return False

    def remove(self, value, warn=True):
        new = Dependency(value)
        old = self.dependencies.get(new.name)
        new_label = new.to_stdout()
        if old is not None:
            old_label = old.to_stdout()
            self.dependencies.pop(new.name)
            self._save()
            stdout.write(red('- ') + old_label)
            return True
        else:
            if warn:
                stdout.write('%s %s' % (new_label, yellow('not installed.')))
            return False

    def get(self, key):
        return self.dependencies.get(key)

    @property
    def dependencies(self):
        if not hasattr(self, '_dependencies'):
            if os.path.exists(self.source):
                self._dependencies = self._load()
            else:
                self._dependencies = {}
        return self._dependencies

    def _load(self):
        dependencies = OrderedDict()
        with open(self.source, 'r') as f:
            for line in f.readlines():
                if line:
                    d = Dependency(line)
                    dependencies[d.name] = d
        self._clean = copy(dependencies)
        return dependencies

    def _save(self):
        with open(self.source, 'w') as f:
            for dependency in self.dependencies.values():
                dependency = str(dependency)
                if not dependency.endswith('\n'):
                    dependency = dependency + '\n'
                f.write(dependency)
        self._clean = copy(self.dependencies)
