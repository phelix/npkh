from common import *
import threading
import time
import os
from optparse import OptionGroup
from ConfigParser import SafeConfigParser
#import optparse
#import ConfigParser
import inspect
import json

log = get_logger(__name__)

def public(func):
    func.rpc_public = True
    return func

class PluginThread(threading.Thread):
    daemon = True
    name = None
    mode = None
    desc = None
    running = False
    threadRunning = False
    options = {}
    helps = {}
    depends = {}
    services = {}
    #version = None

    def __init__(self, mode = 'plugin'):
        if self.name is None:
            raise Exception(str(self.__class__) + " : name not defined")
        self.mode = mode
        self.nameconf = self.mode + '-' + self.name + '.conf'
        self.nameclass = self.mode + self.name.capitalize()
        self.parser = app['parser']
        self.conf = {}
        self._loadconfig()
        threading.Thread.__init__(self)

    def start(self):
        if self.threadRunning: return
        self.threadRunning = True
        threading.Thread.start(self)

    def run(self):
        if self.running: return
        self.start2()

    def start2(self, arg = []):
        log.debug("Plugin %s parent starting" %(self.name))
        self.running = True
        # start depends
        if len(self.depends) > 0:
            if 'plugins' in self.depends:
                for dep in self.depends['plugins']:
                    try:
                        app['plugins'][dep].start()
                    except KeyError:
                        raise Exception(str(self.name) + " 'depends': plugin not found: " + dep)
            if 'services' in self.depends:
                for dep in self.depends['services']:
                    try:
                        app['services'][dep].start()
                    except KeyError:
                        raise Exception(str(self.name) + " 'depends': service not found: " + dep)
        return self.pStart()

    def pStart(self, arg = []):
        log.debug("Plugin %s parent start" %(self.name))
        #time.sleep(1)
        return True

    def stop(self, arg = []):
        if not self.running: return
        log.debug("Plugin %s parent stopping" %(self.name))
        self.running = False
        return self.pStop()

    def pStop(self, arg = []):
        log.debug("Plugin %s parent stop" %(self.name))
        log.info("Plugin %s stopped" %(self.name))
        return True

    def status(self, arg = []):
        return self.pStatus()

    def pStatus(self, arg = []):
        if self.running:
            return "Plugin " + self.name + " running"

    def reload(self, arg = []):
        log.debug("Plugin %s parent reloading" %(self.name))
        return self.pReload()

    def pReload(self, arg = []):
        log.debug("Plugin %s parent reload" %(self.name))
        self.loadconfig()
        return True

    def restart(self, arg = []):
        log.debug("Plugin %s parent restarting" %(self.name))
        return self.pRestart()

    def pRestart(self, arg = []):
        log.debug("Plugin %s parent restart" %(self.name))
        self.stop()
        self.start2()
        return True

    def help(self, *arg):
        return self.pHelp(*arg)

    def pHelp(self, *args):
        if len(args) > 0 and type(args[0]) != list:
            method = args[0]
            if method in self.helps:
                help = self.helps[method][3]
                help += '\n' + method + ' ' + self.helps[method][2]
                return help

        methods = self._getPluginMethods()
        help = '* Available commands for plugin ' + self.name + ' :'
        for method in methods:
            if method in self.helps:
                method = method + ' ' + self.helps[method][2]
            help += '\n' + method
        return help

    def _getPluginMethods(self):
        parents = []
        parentmethods = inspect.getmembers(threading.Thread)
        for (method, value) in parentmethods:
            parents.append(method)

        methods = []
        allmethods = inspect.getmembers(self, predicate=inspect.ismethod)
        for (method, value) in allmethods:
            if method[0] == '_':
                continue
            if method[0] == 'p' and method[1].upper() == method[1]:
                continue
            if method in parents:
                continue
            if method == 'start2': method = 'start'
            if method in self.helps:
                method = method + ' ' + self.helps[method][2]
            methods.append(method)
        methods.sort()
        return methods

    def _loadconfig(self, arg = []):
        # manage services
        for service, value in self.services.iteritems():
            if self.name not in app['services'][service].services:
                app['services'][service].services = {}
            app['services'][service].services[self.name] = value

        # add command line args to the program options + build default configuration data
        defaultConf = '[' + self.name + ']\n'
        group = OptionGroup(app['parser'], self.name.capitalize() + " Options", self.desc)
        for option in self.options:
            value = self.options[option]
            if len(value) == 3:
                help = value[0] + " " + value[2] + ""
                defaultConf += '; ' + value[0] + ' - choices: ' + value[2] + '\n'
            else:
                help = value[0]
                defaultConf += '; ' + value[0] + '\n'
            defaultConf += ';' + option + '=' + str(value[1]) + '\n\n'
            if option != 'start':
                if self.name == 'main':
                    group.add_option('--' + option, '--' + self.name + '.' + option, type='str', help=help, metavar=str(value[1]))
                else:
                    group.add_option('--' + self.name + '.' + option, type='str', help=help, metavar=str(value[1]))
            self.conf[option] = value[1]
        app['parser'].add_option_group(group)

        # create default config if none
        userConfFile = app['path']['conf'] + self.nameconf
        if not os.path.exists(userConfFile):
            if not os.path.exists(app['path']['conf']): # TODO: Note that with Python 3.2+ we can compress this to os.makedirs(app['path']['conf'], exist_ok=True), see http://stackoverflow.com/a/5032238
                os.makedirs(app['path']['conf'])
            fp = open(userConfFile, 'w')
            fp.write(defaultConf)
            fp.close()

        # read user config
        fileconf = SafeConfigParser()
        fileconf.read(userConfFile)

        # set user config
        for option in fileconf.options(self.name):
            self.conf[option] = fileconf.get(self.name, option)

        self.pLoadconfig()

    def pLoadconfig(self, arg = []):
        pass

    # call a plugin method
    def _rpc(self, method, *args, **kwargs): #, module = None):
        #if module is not None and (type(module) == str or type(module) == unicode):
        #    self = __import__(module)
        #elif module is not None:
        #    self = module

        func = getattr(self, method)

        if "api_user" not in kwargs:
            api_user = "public"
        else:
            api_user = kwargs["api_user"]

        log.debug(method, "public function?", hasattr(func, "rpc_public"))

        if api_user != "admin" and not hasattr(func, "rpc_public"):
            raise Exception('Method "' + method + '" not allowed')

        return func(*args)
