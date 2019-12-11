# -*- coding: utf-8 -*-
from __future__ import print_function

DEFAULTHOST = "127.0.0.1"  # 0.0.0.0 allows public access
DEFAULTPORT = "8083"
DEFAULTKEYSERVER = "sks-keyservers.net"

CACHETIMETOLIVEMINUTES = 5
MAXCACHESIZE = 10

"""
The main OpenPGP HTTP Keyserver Protocol functions are 'index' to search for a list
of keys and 'get' to retrieve a pgp key corresponding to a fingerprint. PGP keys are
usually looked up by first doing an 'index' operation and then a 'get' operation
requesting the PGP key by fingerprint. Because of this we need to cache fingerprints
for Namecoin ID lookups so that we know whether a fingerprint belongs to a
Namecoin ID. Unlike normal requests PGP keys for Namecoin IDs might be
downloaded from a custom website as specified in the name value. Also it will be
verified a cached fingerprint is still up to date.
Note: The integrity of the returned data will be validated externally in GPG (e.g.
verifying that a key matches a long fingerprint).

"""

# workaround to make bottle stoppable - this can be cleaned up with bottle 0.13
import wsgiref.simple_server
original_make_server = wsgiref.simple_server.make_server
def my_make_server(*args, **kwargs):
    server = original_make_server(*args, **kwargs)
    args[2].server = server  # app
    return server
wsgiref.simple_server.make_server = my_make_server
# now stop via app.server.shutdown()

def remove_value(dic, value):
    """remove all items with value if any (in place)"""
    for k, v in list(dic.items()):
        if v == value:
           del dic[k]

import re
ALLOWEDRE = "^id/[a-z0-9]+([-]?[a-z0-9])*$"
reg = re.compile(ALLOWEDRE)

import json

try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+
try:
    from urllib2 import urlopen  # Python 2.X
except ImportError:
    from urllib.request import urlopen  # Python 3+

import bottle

from expiringdict import ExpiringDict

import namerpc

import common

if __name__ == "__main__":
    common.app['debug'] = True

import plugin

log = common.get_logger(__name__)

# Code to work as NMControl plugin
class pluginKeyHandler(plugin.PluginThread):
    name = 'keyHandler'
    options = {
        'start' : ['Launch at startup', 1],
        'host' : ['Listen on ip', DEFAULTHOST, '<ip>'],
        'port' : ['Listen on port', DEFAULTPORT, '<port>'],
        'keyserver' : ['Proxy keyserver', DEFAULTKEYSERVER, '<keyserver>'],
    }
    server = None

    def pStart(self):
        if self.server:
            return
        log.debug("Plugin %s parent start" % (self.name))
        self.keyServer = KeyServer()
        self.running = 1
        self.keyServer.start()

    def pStop(self, arg = []):
        log.debug("Plugin %s parent stop" % (self.name))
        if not self.running:
            return True
        self.keyServer.stop()
        self.running = False
        self.server = None
        return True

import pgpdump
def calc_fingerprint(asciiArmored):
    a = pgpdump.AsciiData(asciiArmored)
    p = a.packets()
    n = p.next()
    fpr = "0x" + n.fingerprint.lower()
    log.debug("calc_fingerprint:", fpr)
    return fpr

def validate_fingerprint(fpr, s):
    calculatedFpr = calc_fingerprint(s)
    if not "0x" in fpr:
        fpr = "0x" + fpr
    try:
        assert fpr.lower() == calculatedFpr
    except AssertionError:
        log.debug("validate_fingerprint: Query does not match calculated fingerprint:", fpr.lower(), calculatedFpr)
        raise
    else:
        log.debug("validate_fingerprint: proxy_to_standard_pks: match", calculatedFpr)

class BaseIdRequest(object):
    def __init__(self, name, standardKeyServer):
        if not reg.match(name):
            bottle.abort(400, "Wrong id/ format.")
        self.name = name
        self.standardKeyServer = standardKeyServer

    def get_value(self, name):
        try:
            value = common.app['plugins']['data'].getValueProcessed(name)
        except Exception as e:  # todo: proper error handling in NMControl
            bottle.abort(502, "Backend error (NMControl internal): " + repr(e))
        if value == False:
            bottle.abort(404, "Name not found.")
        log.debug("get_value value:", type(value), value)
        return value

    def get_fpr(self):
        self.value = self.get_value(self.name)

        # fetch fpr
        try:
            fpr = self.value["gpg"]["fpr"]
        except KeyError:
            try:
                fpr = self.value["fpr"]  # untidy?
            except KeyError:
                bottle.abort(415, "No fingerprint found in " + unicode(self.name))
        fpr = fpr.lower()
        # check fpr
        try:
            int(fpr, base=16)
        except ValueError:
            bottle.abort(415, "Bad fingerprint.")
        if len(fpr) < 40:  # 40: sha1
            bottle.abort(415, "Insecure fingerprint.")
        self.fpr = fpr
        return fpr

    def get_index(self):
        #"pub:<keyid>:<algo>:<keylen>:<creationdate>:<expirationdate>:<flags>"

        s = "info:1:1\n"
        s += "pub:" + self.fpr + "\n"

        n = [self.name]
        for f in ["name", "email", "country", "locality"]:
            if f in self.value:
                if type(self.value[f]) == list:
                    v = self.value[f][0]
                elif type(self.value[f]) == dict:
                    v = self.value[f]["default"]
                else:
                    v = self.value[f]
                n.append(quote(v))
        s += "uid:" + " - ".join(n) + "\n"

        log.debug("get_index s:", s)
        return s

    def get_key(self):
        try:
            url = self.value["gpg"]["uri"]
            log.debug("get_key: trying custom key url:", url)
            k = urlopen(url).read()
        except:
            url = ("https://" + self.standardKeyServer +
                   "/pks/lookup?op=get&options=mr&search=0x" + self.fpr)
            log.debug("get_key: trying keyserver url:", url)
            k = urlopen(url).read()
        validate_fingerprint(self.fpr, k)
        log.debug("get_key: ok, len: " + str(len(k)))
        return k

class StandaloneIdRequest(BaseIdRequest):
    def get_value(self, name):
        rpc = namerpc.CoinRpc(connectionType=rpcConnectionType,
                              options=rpcOptions)
        try:
            data = rpc.nm_show(name)
        except namerpc.NameDoesNotExistError:
            bottle.abort(404, "Name not found.")
        except namerpc.RpcError:
            bottle.abort(502, "Backend error (rpc).")

        try:
            data = json.loads(data)
        except TypeError:
            pass
        value = data["value"]
        try:
            value = json.loads(value)
        except TypeError:
            pass
        log.debug("get_value value:", type(value), value)
        return value

class RequestHandler(object):
    def __init__(self, standardKeyServer=DEFAULTKEYSERVER):
        # cache for connecting fingerprints to names - all lowercase so we don't have to handle 0X instead of 0x
        self.idFprs = ExpiringDict(max_len=MAXCACHESIZE, max_age_seconds=60*CACHETIMETOLIVEMINUTES)
        self.standardKeyServer = standardKeyServer
        log.debug("New RequestHandler")

    def proxy_to_standard_pks(self, request):
        """Pass request through to default keyserver."""
        # currently this will break with NMControl as global system DNS because of
        # getaddrinfo not being thread safe
        log.debug("proxying to " + self.standardKeyServer)
        url = request.urlparts._replace(  # _replace is a public function despite the underscore
                        netloc=self.standardKeyServer, scheme="https").geturl()
        log.debug("modified request:", url)
        return urlopen(url).read()

    def lookup_req(self, request):
        search = request.query.search
        op = request.query.op
        return self.lookup(search, op, request=request)

    def lookup(self, search, op, request=None):
        name = None
        if search.startswith("id/"):  # looking up a Namecoin id/ ?
            name = search

        searchFpr = None
        if search.lower() in self.idFprs:  # looking up a cached fingerprint?
            searchFpr = search.lower()

        log.debug("lookup: search:", search, " name:", name, " searchFpr:", searchFpr,
                  " request:", request != None, " op:", op, len(self.idFprs), self.idFprs)
        if not name and not searchFpr:
            # neither looking for a Namecoin id/ nor for a fingerprint - hand over to standard keyserver
            if request:
                log.debug("lookup:standard:", name)
                return self.proxy_to_standard_pks(request)
            else:  # should never happen
                bottle.abort(403, "No request and search not recognized: " + unicode(search))

        # allow index of keys in idFprs
        if searchFpr:
            name = self.idFprs[searchFpr]

        log.debug("lookup: id/:", name, "searchFpr:", searchFpr)

        # handle Namecoin ID lookup
        if not standalone:
            idRequest = IdRequest(name, self.standardKeyServer)
        else:
            idRequest = StandaloneIdRequest(name, self.standardKeyServer)
        if op.lower() == "get":
            validate_fingerprint(search, s)

        fpr = idRequest.get_fpr()

        # if searching by fingerprint make sure to adhere
        if searchFpr and searchFpr != "0x" + fpr:
            bottle.abort(503, "Fingerprint mismatch. Out of date?")

        # keep cache up to date
        remove_value(self.idFprs, name)  # maybe a key was revoked (in place operation)
        cacheFpr = "0x" + fpr.lower()
        self.idFprs[cacheFpr] = name
        log.debug("lookup: updated cache:", name, cacheFpr, len(self.idFprs))

        if op == "index":
            log.debug("lookup:index:", name)
            return idRequest.get_index()
        elif op == "get":
            log.debug("lookup:get:", name)
            return idRequest.get_key()  # will try custom server, then standardKeyServer
        else:
            bottle.abort(501, "Not implemented.")

class KeyServer(object):
    def __init__(self, host=DEFAULTHOST, port=DEFAULTPORT,
                 standardKeyServer=DEFAULTKEYSERVER):
        self.host = host
        self.port = port
        self.standardKeyServer = standardKeyServer
        self.app = bottle.Bottle()
        self.app.route('/pks/lookup', ['GET', 'POST'], self.serve)
        self.app.route('/pks/add', ['GET', 'POST'], self.httpError501)  # as per the hkp spec
        self.rh = RequestHandler(self.standardKeyServer)

    def start(self):
        bottle.run(self.app, host=DEFAULTHOST, port=DEFAULTPORT)

    def stop(self):
        self.app.server.shutdown()  # todo: simplify with bottle v0.13

    def serve(self):
        log.debug(".............. request url:", bottle.request.url)

        return self.rh.lookup_req(bottle.request)

    def httpError501(self):
        bottle.abort(501, "Not implemented.")
